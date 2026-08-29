/**
 * Per-turn network quality (INT-103 acceptance: "RTT/jitter/loss attached to
 * turns"). Pure arithmetic over transport samples so the figures are testable
 * in node without a peer connection.
 *
 * Two decisions worth stating, because both are easy to get subtly wrong:
 *
 * 1. LOSS IS A RATE OVER THE TURN'S OWN WINDOW. WebRTC reports `packetsLost`
 *    and packet counts as CUMULATIVE session counters. Attaching the raw
 *    counter to a turn would make every late turn inherit the whole session's
 *    history — a turn at minute nine would look catastrophic because minute
 *    one was. So a window differences its closing sample against its opening
 *    baseline, and the rate is that delta over the delta in total packets.
 *
 * 2. NO READING IS NOT A PERFECT READING. A window that collected nothing
 *    yields `samples: 0` with zeroed figures, and the caller is expected to
 *    treat that as "unknown", never as "excellent". Emitting a confident 0 ms
 *    RTT for a turn we never measured would be a fabricated measurement
 *    (invariant 20 posture: measurements are measurements or they are absent).
 *
 * Invariant 6: a TurnQuality carries a work id and transport numbers. There
 * is no field here for a transcript, an utterance, a participant name or any
 * other patient-derived value, and none may be added.
 */
import type { TransportSample, TurnQuality } from "./types";

/** An open measurement window for one turn. Treat as opaque. */
export interface QualityWindow {
  readonly workId: number;
  /** Cumulative counters at the moment the turn opened; null if unavailable. */
  readonly baseline: TransportSample | null;
  readonly rttMs: readonly number[];
  readonly jitterMs: readonly number[];
  /** The most recent sample, which closes the window's counter delta. */
  readonly latest: TransportSample | null;
  readonly relayed: boolean;
}

/** Open a window for one turn. The baseline may legitimately be null. */
export function openWindow(workId: number, baseline: TransportSample | null): QualityWindow {
  return {
    workId,
    baseline,
    rttMs: [],
    jitterMs: [],
    latest: null,
    relayed: baseline?.relayed ?? false,
  };
}

/** Fold one reading into an open window. Pure: returns the next window. */
export function addSample(window: QualityWindow, sample: TransportSample): QualityWindow {
  return {
    workId: window.workId,
    // The first sample doubles as the baseline when the turn opened before a
    // candidate pair was selected; otherwise the turn's own start still wins.
    baseline: window.baseline ?? sample,
    rttMs: [...window.rttMs, sample.rttMs],
    jitterMs: [...window.jitterMs, sample.jitterMs],
    latest: sample,
    // Sticky: one relayed sample means the turn ran degraded (files/03 §4.4b
    // treats TCP/TLS relay selection as trigger T4). A later direct sample
    // does not retroactively make the turn clean.
    relayed: window.relayed || sample.relayed,
  };
}

/** The median. Even-length windows take the lower middle — no interpolation
 * inventing a value that was never measured. */
export function median(values: readonly number[]): number {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) / 2)];
}

/**
 * Close a window into the figure attached to the turn.
 *
 * `lossRate` is clamped into [0,1]: counters can go backwards across an ICE
 * restart (a fresh peer connection resets them), and a negative or >1 rate is
 * a measurement artefact, not a finding.
 */
export function closeWindow(window: QualityWindow): TurnQuality {
  const samples = window.rttMs.length;
  return {
    workId: window.workId,
    rttMsP50: median(window.rttMs),
    jitterMsP50: median(window.jitterMs),
    lossRate: lossRate(window.baseline, window.latest),
    relayed: window.relayed,
    samples,
  };
}

function lossRate(baseline: TransportSample | null, latest: TransportSample | null): number {
  if (baseline === null || latest === null) {
    return 0;
  }
  const totalDelta = latest.packetsTotal - baseline.packetsTotal;
  if (totalDelta <= 0) {
    // No packets moved in this window (or the counters restarted): there is
    // no rate to report. Zero here means "nothing observed", and `samples`
    // is what tells the caller which zero this is.
    return 0;
  }
  const lostDelta = latest.packetsLost - baseline.packetsLost;
  if (lostDelta <= 0) {
    return 0;
  }
  return Math.min(1, lostDelta / totalDelta);
}
