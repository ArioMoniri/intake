/**
 * Vizitlerim (02 §4). Two views over the same visits, chosen by a segmented
 * toggle: the Liste (default) is the upcoming group then a Geçmiş (past) group
 * — most recent first, with an honest empty state rather than invented history
 * — and the Takvim is a month grid that marks the days that carry a visit and
 * lets the patient tap a day to read that day's visits below it. Design pass 3:
 * kicker over the groups, xl rhythm between them, air above the hero line.
 *
 * "Today" is read once per render from the injected clock (lib/clock.ts): the
 * device's date in Europe/Istanbul, so the whole screen (the upcoming/past
 * split, the calendar's today marker and its opening month) agrees on one
 * date, and that date is the real one (INT-409). A test passes a fixed clock.
 */
import { useState } from "react";
import { Link, useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { EmptyState } from "@/components/EmptyState";
import { useTabBarClearance } from "@/components/FloatingTabBar";
import { Kicker } from "@/components/Kicker";
import { Segmented, type SegmentedOption } from "@/components/Segmented";
import { statusLabelKey } from "@/components/StatusChip";
import { AppText, Card, RAIL_EDGES, Screen, SecondaryButton } from "@/components/Themed";
import { VisitCalendar } from "@/components/VisitCalendar";
import { VisitCard, formatVisitDate } from "@/components/VisitCard";
import { joinParts } from "@/lib/a11y/labels";
import { MIN_TAP } from "@/lib/a11y/target";
import {
  initialMonth,
  initialSelectedDay,
  longDate,
  pastVisitsRecentFirst,
  visitsOnDay,
  type YearMonth,
} from "@/lib/calendar";
import { deviceClock, todayIso, type Clock } from "@/lib/clock";
import { getLocale, t } from "@/lib/i18n";
import { useSession, type VisitFixture } from "@/lib/session";
import { spacing } from "@/lib/theme";
import { splitVisits } from "@/lib/visits";

type ViewMode = "list" | "calendar";

interface VisitsProps {
  /** Where "today" comes from: the device's clock unless a test fixes one. */
  readonly clock?: Clock;
}

export default function Visits({ clock = deviceClock }: VisitsProps) {
  const router = useRouter();
  const { visits } = useSession();
  const today = todayIso(clock);

  const [view, setView] = useState<ViewMode>("list");
  // Open the calendar on the soonest booked visit, and pre-select it, so a
  // patient with an appointment lands on it rather than on an empty month.
  const [viewMonth, setViewMonth] = useState<YearMonth>(() => initialMonth(visits, today));
  const [selectedDay, setSelectedDay] = useState<string>(() => initialSelectedDay(visits, today));

  // a dateless visit is upcoming, not past (INT-134) — see splitVisits
  const { upcoming } = splitVisits(visits, today);
  const past = pastVisitsRecentFirst(visits, today);
  const dayVisits = visitsOnDay(visits, selectedDay);

  const viewOptions: SegmentedOption[] = [
    { id: "list", label: t("visits.view.list") },
    { id: "calendar", label: t("visits.view.calendar") },
  ];

  /**
   * A card's accessible name (INT-144). Wrapping the card in a Pressable
   * merges its four lines into one element, and RN's derived name drops the
   * status chip; naming it explicitly keeps department, hospital, date AND
   * ladder state in the one sentence a screen-reader user hears.
   */
  const cardLabel = (visit: VisitFixture): string =>
    joinParts(
      visit.department,
      visit.hospital,
      formatVisitDate(visit.date, getLocale()),
      visit.noteStatus === null ? null : t(statusLabelKey(visit.noteStatus)),
    );

  const renderVisit = (visit: VisitFixture) => (
    <Link key={visit.id} href={`/(tabs)/visits/${visit.id}`} asChild>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={cardLabel(visit)}
        accessibilityHint={t("a11y.openHint")}
        style={styles.cardTarget}
      >
        <VisitCard visit={visit} chevron />
      </Pressable>
    </Link>
  );

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: useTabBarClearance() }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("visits.title")}
        </AppText>
        {visits.length === 0 ? (
          <EmptyState icon="calendar" message={t("visits.empty")} />
        ) : (
          <>
            <Segmented
              label={t("visits.view.label")}
              options={viewOptions}
              value={view}
              onChange={(id) => setView(id as ViewMode)}
            />
            {view === "list" ? (
              <>
                {upcoming.length > 0 ? (
                  <View style={styles.section}>
                    {/* Neutral like Oura's quiet group headings (design pass 5)
                        — the accent budget belongs to the screen's one action. */}
                    <Kicker label={t("visits.upcoming")} />
                    {upcoming.map(renderVisit)}
                  </View>
                ) : null}
                {/* Always present, even with nothing in it: the patient asked
                    for their past visits, so "none yet" is the honest answer,
                    not a hidden section (02 §4). */}
                <View style={styles.section}>
                  <Kicker label={t("visits.past")} />
                  {past.length > 0 ? (
                    past.map(renderVisit)
                  ) : (
                    <Card>
                      <AppText role="body" color="inkSoft">
                        {t("visits.pastEmpty")}
                      </AppText>
                    </Card>
                  )}
                </View>
              </>
            ) : (
              <>
                <VisitCalendar
                  visits={visits}
                  todayIso={today}
                  viewMonth={viewMonth}
                  onChangeMonth={setViewMonth}
                  selectedIso={selectedDay}
                  onSelectDay={setSelectedDay}
                />
                <View style={styles.section}>
                  <AppText role="label" heading color="inkSoft">
                    {longDate(selectedDay, getLocale())}
                  </AppText>
                  {dayVisits.length > 0 ? (
                    dayVisits.map(renderVisit)
                  ) : (
                    <AppText role="body" color="inkSoft">
                      {t("visits.calendar.noVisitsOnDay")}
                    </AppText>
                  )}
                </View>
              </>
            )}
          </>
        )}
        {/* Adding is available, not urgent — the Oura register keeps list
            screens free of saturated CTAs (design pass 5). */}
        <SecondaryButton
          label={t("today.addVisit")}
          onPress={() => router.push("/(tabs)/visits/new")}
        />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.xl },
  heroLine: { marginTop: spacing.xl },
  section: { gap: spacing.md },
  // The card inside is far taller than the floor; declaring it keeps the
  // SC 2.5.8 guarantee a property of THIS element rather than of whatever
  // happens to be rendered in it.
  cardTarget: { minHeight: MIN_TAP },
});
