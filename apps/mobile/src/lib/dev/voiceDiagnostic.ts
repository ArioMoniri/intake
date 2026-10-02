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
  /** The tier(s) that spoke, then why George did not — both as tokens. */
  readonly lines: readonly string[];
  readonly hint: string;
}

/**
 * INT-440 — the same dev-only posture for the agent's VOICE. The owner heard
 * the self-hosted lane and could not tell it was not George, because the
 * George fallback was silent by design. In dev, a clip that was not George's
 * says which tier spoke and the closed-set reason George did not (a code token
 * like an HTTP status, never a host or a narrative). Production, a George
 * clip and "no clip yet" all render nothing.
 *
 * @param record the lane record of the clip now playing, or null
 * @param isDev  pass `__DEV__`, never a literal
 */
export function ttsLaneDiagnostic(
  record: ClipLaneRecord | null,
  isDev: boolean,
): TtsLaneDiagnostic | null {
  if (!isDev || record === null || record.lane === "george") {
    return null;
  }
  const served =
    record.tiers.length === 0
      ? t("devVoice.lane.served")
      : `${t("devVoice.lane.served")}${SEPARATOR}${record.tiers.join(" + ")}`;
  return {
    title: t("devVoice.lane.title"),
    lines: [served, `${t("devVoice.lane.georgeMiss")}${SEPARATOR}${record.georgeMiss}`],
    hint: t("devVoice.lane.hint"),
  };
}
