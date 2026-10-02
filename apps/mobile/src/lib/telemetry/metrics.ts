/**
 * Client performance series (INT-145; CLAUDE.md invariants 6, 13, 20).
 *
 * INVARIANT 13 — every id here ALREADY exists in
 * observability/metrics_catalog.yaml: `client.crash_free_sessions` (target
 * ">= 99.5 %"), `client.cold_start_p95_ms`, `client.anr_rate` and
 * `web.core_web_vitals` (labels `[vital]`), all `owner: client`, and since
 * INT-440 `client.dialogue_tts_lane` (labels `[lane, george_miss]`), catalogued
 * in the same PR that emits it. This module emits under the catalogued dotted
 * ids only.
 *
 * THEIR `status` STAYS `planned`, AND THAT IS THE HONEST ANSWER. The catalogue
 * gate (tests/observability/test_metrics_catalog.py) decides "live" by two
 * mechanisms, both Python-only: an AST scan for `prometheus_client` family
 * constructors under packages/ and services/, and a real GET of a served
 * `/metrics`. A React Native client registers no Prometheus family and serves
 * no `/metrics`; it hands readings to an injected sink. Flipping status here
 * would be a claim about an exposition that does not exist — the same reasoning
 * lib/livekit/metrics.ts recorded for the three `net.*` series, and the same
 * posture invariant 20 takes about measurements generally. When an ingest
 * endpoint lands and registers these gauges, that PR promotes them.
 *
 * INVARIANT 6 IS ENFORCED BY TYPE. A sample carries a catalogued id, a number,
 * and — for the one series the catalogue gives a label — a `vital` from a
 * closed set. There is no free-text field and no attribute bag, so there is
 * nowhere a screen name, a URL or an utterance could be put by accident.
 *
 * INVARIANT 20 — A MISSING MEASUREMENT IS ABSENT, NOT ZERO. Crash-free share
 * before the first session is `null`, not 1.0; p95 with no readings is `null`,
 * not 0 ms. An SLI computed over a fabricated 100 % would be quietly wrong in
 * the reassuring direction.
 */

import type { ClipLaneOutcome, GeorgeMiss } from "../dialogue/georgeClip";

export const CLIENT_CRASH_FREE_SESSIONS = "client.crash_free_sessions";
export const CLIENT_COLD_START_P95_MS = "client.cold_start_p95_ms";
export const CLIENT_ANR_RATE = "client.anr_rate";
export const WEB_CORE_WEB_VITALS = "web.core_web_vitals";
/** INT-440: one count per synthesized dialogue clip, by the lane that spoke it
 * (catalogued `labels: [lane, george_miss]`, `status: planned`). */
export const CLIENT_DIALOGUE_TTS_LANE = "client.dialogue_tts_lane";

/** Every id this module is allowed to emit. The emit guard enforces it. */
export const EMITTED_CLIENT_METRIC_IDS: readonly string[] = [
  CLIENT_CRASH_FREE_SESSIONS,
  CLIENT_COLD_START_P95_MS,
  CLIENT_ANR_RATE,
  WEB_CORE_WEB_VITALS,
  CLIENT_DIALOGUE_TTS_LANE,
];

/** The `lane` label's closed value set for `client.dialogue_tts_lane`. */
export const TTS_LANES = ["george", "self_hosted"] as const;
export type TtsLaneLabel = (typeof TTS_LANES)[number];

/** The catalogue gives `web.core_web_vitals` one label, `vital`. This is its
 * closed value set — a label is an enumeration, never free text (the catalogue
 * schema's own PHI-risk label rule takes the same line). */
export const WEB_VITALS = ["CLS", "FCP", "INP", "LCP", "TTFB"] as const;
export type WebVital = (typeof WEB_VITALS)[number];

/** One reading. Ids and numbers only — see the invariant-6 note above. */
export interface ClientMetricSample {
  readonly metricId: string;
  readonly value: number;
  /** Present only for `web.core_web_vitals`, whose catalogued labels are
   * `[vital]`. */
  readonly vital?: WebVital;
  /** Present only for `client.dialogue_tts_lane` (INT-440). */
  readonly lane?: TtsLaneLabel;
  /** `client.dialogue_tts_lane` on the self-hosted lane: why George did not
   * speak — a closed set (georgeClip GEORGE_MISSES), never a narrative. Every
   * other series is catalogued with `labels: []`. */
  readonly georgeMiss?: GeorgeMiss;
}

/** One `client.dialogue_tts_lane` count for one synthesized clip (INT-440). */
export function ttsLaneSample(outcome: ClipLaneOutcome): ClientMetricSample {
  return outcome.lane === "george"
    ? { metricId: CLIENT_DIALOGUE_TTS_LANE, value: 1, lane: "george" }
    : {
        metricId: CLIENT_DIALOGUE_TTS_LANE,
        value: 1,
        lane: "self_hosted",
        georgeMiss: outcome.georgeMiss,
      };
}

export interface ClientMetricSink {
  emit(sample: ClientMetricSample): void;
}

/** Discards everything — the default, so telemetry is opt-in. */
export const noopClientMetricSink: ClientMetricSink = { emit: () => undefined };

/** How many cold-start readings we keep. A long-lived process must not grow an
 * unbounded array, and a p95 over the last 200 launches is the useful one. */
const COLD_START_WINDOW = 200;

/** Counters and readings for one installation's current process. */
export interface PerfState {
  readonly sessions: number;
  readonly crashes: number;
  readonly stalls: number;
  readonly coldStartMs: readonly number[];
}

export function emptyPerfState(): PerfState {
  return { sessions: 0, crashes: 0, stalls: 0, coldStartMs: [] };
}

export function recordSession(state: PerfState): PerfState {
  return { ...state, sessions: state.sessions + 1 };
}

export function recordCrash(state: PerfState): PerfState {
  return { ...state, crashes: state.crashes + 1 };
}

/** One main-thread stall past the watchdog's threshold. See `anrRate`. */
export function recordStall(state: PerfState): PerfState {
  return { ...state, stalls: state.stalls + 1 };
}

/** Fold in one cold-start duration. A reading that is not a finite,
 * non-negative number is not a slow launch, it is a broken clock: dropped. */
export function recordColdStart(state: PerfState, ms: number): PerfState {
  if (!Number.isFinite(ms) || ms < 0) {
    return state;
  }
  const next = [...state.coldStartMs, ms];
  return { ...state, coldStartMs: next.slice(Math.max(0, next.length - COLD_START_WINDOW)) };
}

function ratio(numerator: number, denominator: number): number | null {
  if (denominator <= 0) {
    return null;
  }
  return Math.min(1, Math.max(0, numerator / denominator));
}

/** Crash-free share, or null before the first session. */
export function crashFreeRatio(state: PerfState): number | null {
  return ratio(state.sessions - state.crashes, state.sessions);
}

/**
 * The share of sessions that saw the JS thread stall past the watchdog's
 * threshold. Named against the catalogued `client.anr_rate`, and worth being
 * precise about: a platform ANR is an Android system determination that this
 * app cannot observe from JavaScript. What is measured is a main-thread stall
 * — the closest signal a JS runtime actually has, and the one that moves for
 * the same reasons. `docs/evidence/INT-145.md` records the distinction so the
 * series is never read as the platform's own figure.
 */
export function anrRate(state: PerfState): number | null {
  return ratio(state.stalls, state.sessions);
}

/**
 * p95 cold start by nearest rank — the same no-interpolation rule as
 * `median` in lib/livekit/quality.ts, for the same reason: an interpolated
 * percentile reports a duration no launch ever took.
 */
export function coldStartP95Ms(state: PerfState): number | null {
  const sorted = [...state.coldStartMs].sort((a, b) => a - b);
  if (sorted.length === 0) {
    return null;
  }
  return sorted[Math.min(sorted.length - 1, Math.ceil(0.95 * sorted.length) - 1)];
}

/** One Core Web Vital reading, or null when the vital or value is not one. */
export function webVitalSample(vital: WebVital, value: number): ClientMetricSample | null {
  if (!(WEB_VITALS as readonly string[]).includes(vital) || !Number.isFinite(value)) {
    return null;
  }
  return { metricId: WEB_CORE_WEB_VITALS, value, vital };
}

/** The readings that exist right now. A series with no measurement is absent
 * from the list rather than present with a fabricated value. */
export function perfSamples(state: PerfState): ClientMetricSample[] {
  const readings: [string, number | null][] = [
    [CLIENT_CRASH_FREE_SESSIONS, crashFreeRatio(state)],
    [CLIENT_COLD_START_P95_MS, coldStartP95Ms(state)],
    [CLIENT_ANR_RATE, anrRate(state)],
  ];
  return readings
    .filter((entry): entry is [string, number] => entry[1] !== null)
    .map(([metricId, value]) => ({ metricId, value }));
}

/** Emit the current readings, refusing any id not in the catalogue. */
export function emitPerf(sink: ClientMetricSink, state: PerfState): void {
  for (const sample of perfSamples(state)) {
    if (!EMITTED_CLIENT_METRIC_IDS.includes(sample.metricId)) {
      // Unreachable by construction; the guard keeps it that way if someone
      // later adds a series here without cataloguing it first (invariant 13).
      continue;
    }
    sink.emit(sample);
  }
}
