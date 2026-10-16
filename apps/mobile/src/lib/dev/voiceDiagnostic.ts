/**
 * INT-246 — the `__DEV__` voice-lane banner, as a decision rather than a
 * component.
 *
 * DialogueGate argues, correctly, that a patient who never asked for voice
 * should not be handed a failure notice for it: nothing was attempted, so
 * there is nothing to apologise for. That argument is about the patient. It
 * does not cover the engineer holding the phone, for whom the same silence
 * makes a dead SSH tunnel and an unbuilt screen look identical — which is the
 * incident this issue closes.
 *
 * So the notice is dev-only, and the `__DEV__` gate lives here, in a pure
 * function with no react-native import, where a test can hold it: with
 * `isDev` false this returns null and the component that calls it renders
 * nothing. Production behaviour is not "the banner styled away"; it is the
 * banner never existing.
 *
 * It is also quiet when there is nothing to say: while the probe is still in
 * flight (`report === null`) and when a lane actually answered. A dev banner
 * that appears on a healthy run is a banner people learn to ignore.
 */
import type { ClipLaneRecord } from "@/lib/dialogue/georgeClip";
import { t } from "@/lib/i18n";

import type { ProbeFailure, ReachabilityReport } from "./hosts";

export interface VoiceDiagnostic {
  readonly title: string;
  readonly body: string;
  /** One line per candidate base, in the order the probe walked them. */
  readonly lines: readonly string[];
  readonly hint: string;
}

/** " — " is the visual separator only; nothing here is an accessible name. */
const SEPARATOR = " — ";

function reason(failure: ProbeFailure): string {
  switch (failure.kind) {
    case "timeout":
      return t("devVoice.reason.timeout");
    case "refused":
      return t("devVoice.reason.refused");
    case "status":
      // Concatenated rather than interpolated into the catalogue: the
      // catalogue stays interpolation-free (i18n/index.ts), and an HTTP
      // status is a token, not a quantity — no grouping, no locale digits.
      return `${t("devVoice.reason.status")} ${String(failure.status)}`;
  }
}

/**
 * The banner's content, or null when there must be no banner at all.
 *
 * @param report the finished ASR probe, or null while it is still running
 * @param isDev  pass `__DEV__`, never a literal — see e2e/voiceFallback.spec
 */
export function voiceDiagnostic(
  report: ReachabilityReport | null,
  isDev: boolean,
): VoiceDiagnostic | null {
  if (!isDev) {
    return null; // production: the quiet fallback stands, unchanged
  }
  if (report === null || report.base !== null) {
    return null; // still probing, or voice is up — nothing to report
  }
  const lines =
    report.probes.length === 0
      ? [t("devVoice.noCandidates")]
      : report.probes.map((probe) =>
          probe.failure === null ? probe.base : `${probe.base}${SEPARATOR}${reason(probe.failure)}`,
        );
  return {
    title: t("devVoice.title"),
    body: t("devVoice.body"),
    lines,
    hint: t("devVoice.hint"),
  };
}

export interface TtsLaneDiagnostic {
  readonly title: string;
  /** The lane that spoke, why George did not (fallback only), then the
   * measured timings — all as tokens. */
  readonly lines: readonly string[];
  /** What would bring George back; only on a fallback clip. */
  readonly hint: string | null;
}

/** The turn's measurements, when the hook has them (INT-440). */
export interface VoiceTiming {
  /** Turn start (question on screen) → the clip audibly playing. */
  readonly audioStartMs: number | null;
  /** The loudest microphone level metered in this turn, in dB. */
  readonly micPeakDb: number | null;
  /** End of one clip → start of the next within this turn, in ms. */
  readonly clipGapsMs?: readonly number[];
}

function laneToken(record: ClipLaneRecord): string {
  switch (record.lane) {
    case "george":
      return "elevenlabs-live";
    case "elevenlabs_bundled":
      return "elevenlabs-bundled";
    case "self_hosted":
      return record.tiers.length === 0 ? "self-hosted" : record.tiers.join(" + ");
  }
}

/**
 * INT-440 — the same dev-only posture for the agent's VOICE. The owner heard
 * the self-hosted lane and could not tell it was not George, because the
 * George fallback was silent by design. In dev, every clip names the lane that
 * spoke it (`elevenlabs-bundled`, `elevenlabs-live`, or the self-hosted tier),
 * a fallback adds the closed-set reason George did not (a code token like an
 * HTTP status, never a host or a narrative), and the turn's measured audio
 * start and microphone peak ride along. Production and "no clip yet" render
 * nothing.
 *
 * @param record the lane record of the clip now playing, or null
 * @param isDev  pass `__DEV__`, never a literal
 * @param timing the turn's measurements, when known
 */
export function ttsLaneDiagnostic(
  record: ClipLaneRecord | null,
  isDev: boolean,
  timing?: VoiceTiming,
): TtsLaneDiagnostic | null {
  if (!isDev || record === null) {
    return null;
  }
  const lines = [`${t("devVoice.lane.served")}${SEPARATOR}${laneToken(record)}`];
  if (record.lane === "self_hosted") {
    lines.push(`${t("devVoice.lane.georgeMiss")}${SEPARATOR}${record.georgeMiss}`);
  }
  // Concatenated tokens, as the HTTP status above: the catalogue stays
  // interpolation-free and a measurement is not a localised quantity.
  if (timing?.audioStartMs != null) {
    lines.push(`${t("devVoice.lane.audioStart")}${SEPARATOR}${String(timing.audioStartMs)} ms`);
  }
  if (timing?.clipGapsMs !== undefined && timing.clipGapsMs.length > 0) {
    lines.push(`${t("devVoice.lane.clipGaps")}${SEPARATOR}${timing.clipGapsMs.join(", ")} ms`);
  }
  if (timing?.micPeakDb != null) {
    lines.push(`${t("devVoice.lane.micPeak")}${SEPARATOR}${String(timing.micPeakDb)} dB`);
  }
  const fallback = record.lane === "self_hosted";
  return {
    title: t(fallback ? "devVoice.lane.title" : "devVoice.lane.titleOk"),
    lines,
    hint: fallback ? t("devVoice.lane.hint") : null,
  };
}
