/**
 * INT-497 — the `__DEV__` readout of what the dialogue's turns cost.
 *
 * The turn timeline (lib/dialogue/turnTimeline.ts) measures, on the device,
 * the three figures the owner's order names. The app writes to no console and
 * ships no metrics ingest, so this short caption is how an engineer holding
 * the phone reads them — and how docs/evidence/INT-497.md gets its "after
 * deploy" table from a real device session.
 *
 * Dev only, decided here in a pure function as voiceDiagnostic.ts decides its
 * banner: with `isDev` false this returns null and the screen renders nothing.
 * Durations only; nothing the patient said can reach it.
 */
import { t } from "@/lib/i18n";

import type { TimelineSummary } from "../dialogue/turnTimeline";

/** A duration as one unbreakable atom, whole milliseconds, no grouping. An
 * absent measurement is a dash, never a zero. */
function ms(value: number | null): string {
  return value === null ? "—" : `${String(Math.round(value))} ms`;
}

/** The readout's lines, or null when there must be no readout at all. */
export function turnTimelineReadout(
  summary: TimelineSummary,
  isDev: boolean,
): readonly string[] | null {
  if (!isDev || summary.turns === 0) {
    return null;
  }
  return [
    t("devVoice.timeline.title"),
    `${t("devVoice.timeline.firstAudio")}: p50 ${ms(summary.firstAudioP50Ms)} · p95 ${ms(summary.firstAudioP95Ms)}`,
    `${t("devVoice.timeline.join")}: ${ms(summary.joinMaxMs)}`,
    `${t("devVoice.timeline.asr")}: p50 ${ms(summary.asrP50Ms)} · p95 ${ms(summary.asrP95Ms)}`,
  ];
}
