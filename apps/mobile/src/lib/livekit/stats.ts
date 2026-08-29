/**
 * WebRTC statistics → one TransportSample (INT-103). Pure, so the parsing is
 * unit-tested in node against captured stat shapes rather than against a live
 * peer connection.
 *
 * The readings and where they come from (W3C webrtc-stats):
 *   - RTT      `candidate-pair.currentRoundTripTime`, in SECONDS → ms here.
 *              Only the SELECTED pair counts; a nominated-but-not-selected
 *              pair reports the RTT of a path we are not using.
 *   - jitter   `inbound-rtp(kind: audio).jitter`, in SECONDS → ms here.
 *   - loss     `inbound-rtp.packetsLost` against packets received + sent.
 *              Cumulative counters; quality.ts differences them per turn.
 *   - relayed  the selected pair's local candidate is a relay, or the pair
 *              reports a `relayProtocol`. files/03 §4.4b treats TCP/TLS relay
 *              selection as degradation trigger T4, not a success.
 *
 * The seconds→milliseconds conversions are the reason this is a tested pure
 * function and not three lines inlined in the adapter: reporting a 0.042 s
 * RTT as "0.042 ms" is silent, plausible and wrong in the direction that
 * makes a bad network look perfect.
 *
 * Invariant 6: only transport counters are read. Nothing here touches a
 * track label, a participant identity or any other patient-derived string.
 */
import type { TransportSample } from "./types";

/** The structural slice of an RTCStats entry this parser reads. */
export interface RtcStatsEntry {
  readonly type: string;
  readonly id?: string;
  readonly kind?: string;
  readonly selected?: boolean;
  readonly nominated?: boolean;
  readonly state?: string;
  readonly currentRoundTripTime?: number;
  readonly localCandidateId?: string;
  readonly relayProtocol?: string;
  readonly candidateType?: string;
  readonly jitter?: number;
  readonly packetsLost?: number;
  readonly packetsReceived?: number;
  readonly packetsSent?: number;
}

const SECONDS_TO_MS = 1000;

/**
 * Fold a flat list of stats entries into one sample.
 *
 * Returns null when no selected candidate pair exists — ICE has not settled,
 * so there is no path to measure. Null means "no reading"; the caller must
 * not read it as a good one.
 */
export function parseTransportStats(entries: readonly RtcStatsEntry[]): TransportSample | null {
  const pair = selectedPair(entries);
  if (pair === null) {
    return null;
  }
  const localCandidate = entries.find(
    (entry) => entry.type === "local-candidate" && entry.id === pair.localCandidateId,
  );

  let jitterMs = 0;
  let packetsLost = 0;
  let packetsTotal = 0;
  for (const entry of entries) {
    if (entry.type === "inbound-rtp" && entry.kind === "audio") {
      jitterMs = Math.max(jitterMs, (entry.jitter ?? 0) * SECONDS_TO_MS);
      packetsLost += entry.packetsLost ?? 0;
      packetsTotal += entry.packetsReceived ?? 0;
    } else if (entry.type === "outbound-rtp" && entry.kind === "audio") {
      packetsTotal += entry.packetsSent ?? 0;
    }
  }

  return {
    rttMs: (pair.currentRoundTripTime ?? 0) * SECONDS_TO_MS,
    jitterMs,
    packetsLost,
    // Lost packets never arrived, so they are not in `packetsReceived`. The
    // denominator for a loss RATE is expected packets — received plus lost.
    packetsTotal: packetsTotal + packetsLost,
    relayed: pair.relayProtocol !== undefined || localCandidate?.candidateType === "relay",
  };
}

/**
 * The pair actually carrying media. `selected` is the authoritative flag;
 * a nominated succeeded pair is the fallback for stacks that omit it.
 */
function selectedPair(entries: readonly RtcStatsEntry[]): RtcStatsEntry | null {
  const pairs = entries.filter((entry) => entry.type === "candidate-pair");
  return (
    pairs.find((entry) => entry.selected === true) ??
    pairs.find((entry) => entry.nominated === true && entry.state === "succeeded") ??
    null
  );
}

/** Flatten one or more RTCStatsReport-shaped maps into a plain list. */
export function flattenReports(
  reports: readonly (ReadonlyMap<string, unknown> | undefined)[],
): RtcStatsEntry[] {
  const entries: RtcStatsEntry[] = [];
  for (const report of reports) {
    if (report === undefined) {
      continue;
    }
    for (const value of report.values()) {
      if (typeof value === "object" && value !== null && "type" in value) {
        entries.push(value as RtcStatsEntry);
      }
    }
  }
  return entries;
}
