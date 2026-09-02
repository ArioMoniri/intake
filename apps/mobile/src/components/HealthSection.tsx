/**
 * Sağlık verileri section on Profilim (INT-208). Renders only after the
 * device-local health consent is ON (the parent gates it). States are
 * honest, never dead buttons: Expo Go gets a calm guidance block saying a
 * development build is needed; a device without the platform health app
 * gets one quiet line; denied permission says where to change it. With data
 * available it shows the last-7-days summary — numbers only, never
 * interpreted (invariant 2 posture: no "iyi/kötü") — and a patient-confirmed
 * "Vizite ekleyin" action that appends the labelled block to the next
 * visit's note draft through the existing note reducer. Nothing here calls
 * a server, logs a metric or persists anything.
 */
import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
import { AppText, Card, Hairline, SecondaryButton } from "@/components/Themed";
import { getHealthConnector, lastSevenDayRange, summaryNoteLines } from "@/lib/health";
import type { HealthAvailability, HealthSummary } from "@/lib/health";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

type AttachStep = "idle" | "confirm" | "done";

export function HealthSection() {
  const { visits, updateNote, locale } = useSession();
  const [availability, setAvailability] = useState<HealthAvailability | null>(null);
  const [summary, setSummary] = useState<HealthSummary | null>(null);
  const [readFailed, setReadFailed] = useState(false);
  const [attachStep, setAttachStep] = useState<AttachStep>("idle");

  useEffect(() => {
    let cancelled = false;
    const connector = getHealthConnector();
    setAvailability(null);
    setSummary(null);
    setReadFailed(false);
    void (async () => {
      const result = await connector.available();
      if (cancelled) {
        return;
      }
      setAvailability(result);
      if (result.status !== "ok") {
        return;
      }
      try {
        const next = await connector.readSummary(lastSevenDayRange(new Date()));
        if (!cancelled) {
          setSummary(next);
        }
      } catch {
        if (!cancelled) {
          setReadFailed(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [locale]);

  if (availability === null) {
    return (
      <Card>
        <AppText role="caption" color="inkSoft">
          {t("health.loading")}
        </AppText>
      </Card>
    );
  }

  if (availability.status === "needs_dev_build") {
    return (
      <GuidanceBlock
        kickerKey="health.guide.devBuild.kicker"
        titleKey="health.guide.devBuild.title"
        bodyKey="health.guide.devBuild.body"
      />
    );
  }

  if (availability.status === "platform_unsupported") {
    return (
      <Card>
        <AppText role="body" color="inkSoft">
          {t("health.unsupported")}
        </AppText>
      </Card>
    );
  }

  if (availability.status === "permission_denied") {
    return (
      <Card>
        <AppText role="body" color="inkSoft">
          {t("health.permissionDenied")}
        </AppText>
      </Card>
    );
  }

  if (readFailed) {
    return (
      <Card>
        <AppText role="body" color="inkSoft">
          {t("health.readFailed")}
        </AppText>
      </Card>
    );
  }

  if (summary === null) {
    return (
      <Card>
        <AppText role="caption" color="inkSoft">
          {t("health.loading")}
        </AppText>
      </Card>
    );
  }

  const hasData =
    summary.steps.length > 0 || summary.restingHeartRate !== null || summary.sleepHours !== null;
  if (!hasData) {
    return (
      <Card>
        <AppText role="body" color="inkSoft">
          {t("health.noData")}
        </AppText>
      </Card>
    );
  }

  // Same "next visit" rule as Bugün: the first visit still being prepared.
  const targetVisit = visits.find((v) => v.noteStatus === "draft" || v.noteStatus === null) ?? null;

  const confirmAttach = () => {
    if (targetVisit === null) {
      return;
    }
    updateNote(targetVisit.id, { type: "attachHealth", lines: summaryNoteLines(summary, locale) });
    setAttachStep("done");
  };

  return (
    <View style={styles.section}>
      <Card style={styles.summaryCard}>
        {summary.steps.length > 0 ? (
          <View style={styles.metricBlock}>
            <Kicker label={t("health.steps.label")} />
            {summary.steps.map((day) => (
              <View key={day.dateISO} style={styles.row}>
                <AppText role="caption" color="inkSoft">
                  {day.dateISO}
                </AppText>
                <AppText role="body">{day.value}</AppText>
              </View>
            ))}
          </View>
        ) : null}
        {summary.restingHeartRate !== null ? (
          <>
            <Hairline />
            <View style={styles.row}>
              <AppText role="body" color="inkSoft">
                {t("health.rhr.label")}
              </AppText>
              <AppText role="body">{summary.restingHeartRate}</AppText>
            </View>
          </>
        ) : null}
        {summary.sleepHours !== null ? (
          <>
            <Hairline />
            <View style={styles.row}>
              <AppText role="body" color="inkSoft">
                {t("health.sleep.label")}
              </AppText>
              <AppText role="body">{summary.sleepHours}</AppText>
            </View>
          </>
        ) : null}
      </Card>
      {attachStep === "done" ? (
        <AppText role="caption" color="inkSoft">
          {t("health.attach.done")}
        </AppText>
      ) : targetVisit === null ? (
        <AppText role="caption" color="inkFaint">
          {t("health.attach.noVisit")}
        </AppText>
      ) : attachStep === "confirm" ? (
        <View style={styles.confirmBlock}>
          <AppText role="body">{t("health.attach.confirm")}</AppText>
          <SecondaryButton label={t("health.attach.yes")} onPress={confirmAttach} />
          <SecondaryButton label={t("health.attach.no")} onPress={() => setAttachStep("idle")} />
        </View>
      ) : (
        <SecondaryButton label={t("health.attach.cta")} onPress={() => setAttachStep("confirm")} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.md },
  summaryCard: { gap: spacing.sm },
  metricBlock: { gap: spacing.xs + 2 },
  // Wraps (INT-295): the value is pinned to the far end, and a measurement
  // pushed off the right edge is a clinical fact the patient cannot read.
  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.sm,
  },
  confirmBlock: { gap: spacing.sm },
});
