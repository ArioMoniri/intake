/**
 * Per-turn network telemetry (INT-103; CLAUDE.md invariants 6 and 13).
 *
 * Invariant 13 says every emitted metric must exist in the metrics catalogue.
 * All three series this client produces ALREADY exist in
 * observability/metrics_catalog.yaml — `net.rtt_ms`, `net.jitter_ms` and
 * `net.packet_loss_ratio`, each catalogued as "per turn" with `labels: []`
 * and `owner: voice-runtime`. This module therefore adds NOTHING to the
 * catalogue; it emits against ids that are already there, under their exact
 * catalogued names.
 *
 * Their catalogued `status` stays `planned`, and that is deliberate. The
 * catalogue gate (tests/observability/test_metrics_catalog.py) proves status
 * honest in both directions against the Prometheus registry served by the
 * Python services — "live" means a family observably served on /metrics. This
 * client registers no Prometheus family and serves no /metrics; it hands
 * readings to an injected sink, and the voice-runtime promotes these ids to
 * `live` when it starts serving them. Flipping status here would be a claim
 * about an exposition that does not exist yet.
 *
 * INVARIANT 6 IS ENFORCED BY TYPE. A `MetricSample` carries a catalogued
 * metric id, a number, and a session/turn id — and nothing else. There is no
 * free-text field, no label map, and no attribute bag, so there is nowhere a
 * transcript, an utterance, a participant name or a phone number could be put
 * even by accident. The catalogued labels for these three ids are `[]`, which
 * this shape matches exactly.
 */
import type { TurnQuality } from "./types";

/**
 * The catalogued metric ids this client emits, in their OTel dotted form
 * exactly as `observability/metrics_catalog.yaml` records them.
 */
export const NET_RTT_MS = "net.rtt_ms";
export const NET_JITTER_MS = "net.jitter_ms";
export const NET_PACKET_LOSS_RATIO = "net.packet_loss_ratio";

/** Every metric id this module is allowed to emit. The sink enforces it. */
export const EMITTED_METRIC_IDS: readonly string[] = [
  NET_RTT_MS,
  NET_JITTER_MS,
  NET_PACKET_LOSS_RATIO,
];

/**
 * One reading. Ids only — see the invariant-6 note above for why this type
 * has no room for anything else.
 */
export interface MetricSample {
  /** A catalogued id from EMITTED_METRIC_IDS. */
  readonly metricId: string;
  readonly value: number;
  /** Opaque session identifier. A uuid, never a name or a phone number. */
  readonly sessionId: string;
  /** The turn this reading belongs to. */
  readonly workId: number;
}

/** Where readings go. Wiring supplies the real one; tests supply a spy. */
export interface MetricSink {
  emit(sample: MetricSample): void;
}

/** A sink that discards everything — the default, so telemetry is opt-in. */
export const noopMetricSink: MetricSink = { emit: () => undefined };

/**
 * Turn one closed quality window into catalogued readings.
 *
 * A window with no samples emits NOTHING. Emitting a confident zero for a
 * turn we never measured would put a fabricated measurement into the series
 * (invariant 20's posture: a measurement is a measurement or it is absent),
 * and an SLI computed over it would be quietly wrong.
 *
 * `relayed` is deliberately not emitted: no catalogued series exists for it,
 * and inventing one here would breach invariant 13. It stays a field on the
 * TurnQuality the caller attaches to the turn, where the degradation policy
 * (files/03 §4.4b trigger T4) can read it without a new Prometheus family.
 */
export function turnQualitySamples(sessionId: string, quality: TurnQuality): MetricSample[] {
  if (quality.samples === 0) {
    return [];
  }
  const base = { sessionId, workId: quality.workId };
  return [
    { ...base, metricId: NET_RTT_MS, value: quality.rttMsP50 },
    { ...base, metricId: NET_JITTER_MS, value: quality.jitterMsP50 },
    { ...base, metricId: NET_PACKET_LOSS_RATIO, value: quality.lossRate },
  ];
}

/** Emit a closed window's readings, refusing any id not in the catalogue. */
export function emitTurnQuality(sink: MetricSink, sessionId: string, quality: TurnQuality): void {
  for (const sample of turnQualitySamples(sessionId, quality)) {
    if (!EMITTED_METRIC_IDS.includes(sample.metricId)) {
      // Unreachable by construction; the guard keeps it that way if someone
      // later adds a series here without cataloguing it first (invariant 13).
      continue;
    }
    sink.emit(sample);
  }
}
