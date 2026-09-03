/**
 * INT-243 — the dev TTS lane as an ordered ladder, behind config.
 *
 * files/03 §4.9.1 rows 10-11 pin `openbmb/VoxCPM2` as the TTS for both the
 * cached-clip and the dynamic path; row 12, `freyavoice/Freya-TTS`, is the
 * low-footprint fallback selected at session start. Until INT-243 the client
 * hardcoded one port (8803, Freya) and had nowhere to put a second tier.
 *
 * So: VoxCPM2 serves on 8805, Freya keeps serving on 8803, and this module is
 * the seam between them. The order and the ports come from app.json
 * `extra.ttsLanes`; the built-in order is the default, not a hardcode you
 * have to edit code to change.
 *
 * INT-249 — a lane must prove it can SPEAK, not merely answer. INT-243
 * selected the first tier whose /health answered, which is fine when a dead
 * tier is dead and wrong when it is alive and unusable. Measured on the host,
 * both lanes tunnelled and both /health-green: 8805 timed out at 8.0 s with
 * 0 bytes, 8803 returned 200 with 276,524 bytes in 1.21 s. VoxCPM2 runs on
 * CPU because the GPU is a nearly-full MIG slice (INT-243 recorded RTF ~4.06
 * there and rightly did not force it), so it passes every health probe and
 * cannot finish a turn. Health-only selection therefore picked the lane the
 * patient waits on.
 *
 * Three things change and nothing else does:
 *   - selection times a real short synthesis against files/03 §4.4's stated
 *     turn round-trip for `residency_tr` (`TURN_ROUND_TRIP_BUDGET_MS` in
 *     tts.ts, which records why that figure and not §4.5's TTS-stage row)
 *     and skips a lane that cannot make it, healthy or not;
 *   - the choice is cached for the session and re-probed on failure, so one
 *     lane wedging mid-visit costs a worse voice rather than the visit;
 *   - every synthesis is capped and falls through to the next tier.
 * The ladder's intent is untouched: VoxCPM2 still wins whenever it is fast.
 *
 * INT-294 — and admission must fit the budget the clip deadline allots it.
 * Measured on the host against the live dev daemons on 2 Sep 2026, the serial
 * walk cost 4024 ms of a 4048 ms clip deadline before the first syllable:
 * 1721 ms on a health-green VoxCPM2 that cannot speak, 1505 ms on a
 * configured host the tunnel does not reach, and 798 ms on the Freya that was
 * going to win from the start (docs/evidence/INT-294.md). It won by 24 ms on
 * the host and lost about as often inside React Native, and a lost race then
 * muted the whole visit. Two changes, both about not re-deriving what is
 * already known:
 *   - the walk is a RACE resolved by RANK, not a queue: every candidate is
 *     measured at once and the highest-ranked admissible one wins, so the
 *     ladder costs ONE admission instead of one per (tier, host) pair;
 *   - a host that answers nothing is quarantined for the session, so it
 *     cannot charge the health cap again to say nothing again.
 * Neither changes which lane wins, only how long it takes to say so.
 *
 * Deliberately NOT here: how a clip is chunked, shaped or assembled. That is
 * INT-237's `speechShaping.ts` on branch int-237-tts-quality, still unmerged.
 * This module owns the endpoint and the fallback and stops there, so the two
 * changes compose instead of fighting: `synthesizeOnLane` is the same POST
 * `synthesizeWav` performs, against a base this module resolved.
 *
 * Invariant 22 is tier-independent: `assertSpeakableTr` is re-used verbatim
 * from tts.ts and throws before any request leaves the app, whichever model
 * is about to answer. VoxCPM2's own normaliser is disabled server-side and
 * its daemon rejects digits too (files/03 §4.9.6) — this is the third of the
 * three guards, not the only one.
 */
import {
  SYNTHESIZE_TIMEOUT_MS,
  TURN_ROUND_TRIP_BUDGET_MS,
  assertSpeakableTr,
  type SynthesizeOptions,
} from "./tts";

export interface TtsLaneSpec {
  /** Stable id for logs and health output — "voxcpm2", "freya". */
  readonly id: string;
  readonly port: number;
}

/** A lane spec bound to one concrete host base. */
export interface TtsLaneBase {
  readonly id: string;
  readonly base: string;
}

/**
 * The default ladder: VoxCPM2 first (files/03 §4.9.1 rows 10-11), Freya
 * second (row 12). Overridable per install through app.json.
 */
export const DEFAULT_TTS_LANES: readonly TtsLaneSpec[] = Object.freeze([
  Object.freeze({ id: "voxcpm2", port: 8805 }),
  Object.freeze({ id: "freya", port: 8803 }),
]);

/**
 * Reads an app.json `extra.ttsLanes` value into a lane ladder. Absent or
 * empty means the default order; malformed throws, because a TTS lane that
 * quietly invents a port is worse than one that refuses to start.
 */
export function parseTtsLanes(raw: unknown): readonly TtsLaneSpec[] {
  if (raw === undefined || raw === null) {
    return DEFAULT_TTS_LANES;
  }
  if (!Array.isArray(raw)) {
    throw new Error("tts_lanes_malformed");
  }
  if (raw.length === 0) {
    return DEFAULT_TTS_LANES;
  }
  return raw.map((entry) => {
    if (typeof entry !== "object" || entry === null) {
      throw new Error("tts_lanes_malformed");
    }
    const { id, port } = entry as { id?: unknown; port?: unknown };
    if (typeof id !== "string" || id.length === 0) {
      throw new Error("tts_lanes_malformed");
    }
    if (typeof port !== "number" || !Number.isInteger(port) || port <= 0 || port > 65535) {
      throw new Error("tts_lanes_malformed");
    }
    return { id, port };
  });
}

/**
 * Every (tier, host) base to try, in order: the whole ladder for the first
 * host, then the whole ladder for the next. Tier order dominates host order —
 * a reachable Freya on the dev Mac must not beat a reachable VoxCPM2 there.
 */
export function laneCandidates(
  hostUri: string | undefined,
  extraHosts: readonly string[],
  lanes: readonly TtsLaneSpec[] = DEFAULT_TTS_LANES,
): TtsLaneBase[] {
  const hosts: string[] = [];
  if (hostUri) {
    const host = hostUri.split(":")[0];
    // tunnel mode gives an exp.direct name with no route back to the Mac
    if (!host.endsWith(".exp.direct")) {
      hosts.push(host);
    }
  }
  for (const host of extraHosts) {
    if (!hosts.includes(host)) {
      hosts.push(host);
    }
  }
  return lanes.flatMap((lane) =>
    hosts.map((host) => ({ id: lane.id, base: `http://${host}:${lane.port}` })),
  );
}

/**
 * The utterance every lane is asked to speak before it is trusted with a
 * turn: one short Turkish word, numeral-free like everything else that
 * crosses this boundary (invariant 22), and nothing a patient ever hears —
 * the bytes are measured and dropped, never cached and never written
 * (invariant 3's posture applies to agent audio here by construction: there
 * is no path from a probe to the filesystem).
 *
 * Short on purpose: a long probe measures the utterance, a one-word probe
 * measures the lane. Measured on the host, this word costs 1.03 s on Freya
 * and 3.99 s on the CPU-bound VoxCPM2 — the two tiers separate on it by
 * almost 4×, with the budget cleanly between them.
 */
export const LANE_PROBE_TEXT = "Merhaba";

/**
 * Cap on admitting ONE lane — health leg and probe synthesis together.
 *
 * Not a new duration. `clipDeadlineMs` is
 * `TURN_ROUND_TRIP_BUDGET_MS + sentences × SYNTHESIZE_TIMEOUT_MS`, and tts.ts
 * says in words what that decomposition means: "ONE lane admission plus ONE
 * synthesis per sentence". The deadline has therefore always allotted
 * admission exactly one `TURN_ROUND_TRIP_BUDGET_MS`; INT-294 is the discovery
 * that admission never honoured the figure the deadline was computed from.
 * Replaying the owner's walkthrough on the fake clock, the walk cost 4024 ms
 * of a 4048 ms deadline (docs/evidence/INT-294.md).
 */
export const ADMISSION_BUDGET_MS = TURN_ROUND_TRIP_BUDGET_MS;

/**
 * Cap on the /health leg alone, inside the admission budget above. Health is
 * a cheap GET whose only job is to tell a refused socket from a slow model,
 * so it gets a fraction of the admission and never the whole of it.
 */
export const HEALTH_TIMEOUT_MS = 1500;

/** The host part of a lane base — the unit a reachability verdict is about. */
export function laneHost(base: string): string {
  return /^https?:\/\/([^/]+):\d+$/.exec(base)?.[1] ?? base;
}

/** Why a lane was or was not admitted to the session. */
export type LaneVerdict =
  /** Answered /health and spoke inside the budget. */
  | "ok"
  /** /health answered, and answered non-2xx. The daemon is there. */
  | "unhealthy"
  /**
   * Nothing answered at all — refused, DNS, or silent past the cap. INT-294
   * splits this out of `unhealthy` because the two justify different things:
   * a 503 is one daemon saying no and tells you nothing about its neighbours
   * on the same box, while a socket that answers nothing is a statement about
   * the HOST, and a host that says nothing once will say nothing again.
   */
  | "unreachable"
  /** Healthy, but could not produce audio inside the budget. THE defect. */
  | "over_budget"
  /** Healthy and prompt, and answered with nothing. */
  | "silent"
  /** Healthy, and /synthesize answered non-2xx. */
  | "error"
  /**
   * The walk found its winner and stopped waiting for this one. Carries no
   * information: it is dropped from the measurements and never reaches the
   * ledger, because "I stopped listening" is not a verdict on a lane.
   */
  | "aborted";

export interface LaneMeasurement {
  readonly id: string;
  readonly base: string;
  /** Measured probe milliseconds, or null when it never got that far. */
  readonly ms: number | null;
  readonly verdict: LaneVerdict;
}

export interface LaneProbeOptions {
  /** Cap on the /health leg, inside the admission budget below. */
  timeoutMs?: number;
  /**
   * Cap on admitting ONE lane, health leg included — the blueprint's turn
   * round-trip.
   *
   * INT-249 applied this to the probe synthesis only, so a lane whose /health
   * was slow could cost `timeoutMs + budgetMs` before the ladder moved on.
   * It covers both legs now, which is what lets `selectTtsLane` promise that
   * the WHOLE walk fits inside one admission: every leg runs at once and no
   * leg can outlast the budget.
   */
  budgetMs?: number;
  fetchImpl?: typeof fetch;
  now?: () => number;
  /** Abandons an admission already in flight — the walk found its winner. */
  signal?: AbortSignal;
  /** Called once per lane that answered, as it answers (INT-294's ledger). */
  onMeasured?: (measurement: LaneMeasurement) => void;
}

/**
 * Ask one lane to SPEAK, and time it.
 *
 * This is the whole of INT-249 in one function. Selection used to end at
 * /health, and /health is the one thing a wedged VoxCPM2 does well: measured
 * on the host with both lanes tunnelled, 8805 answered its probe in
 * milliseconds and then took 8.0 s over a synthesis and returned 0 bytes,
 * while 8803 answered in 1.21 s. Health-only selection preferred the lane
 * that cannot finish a turn, and the patient watched a spinner.
 *
 * So: /health first, because it is cheap and it tells a refused socket from
 * a slow model; then a real short synthesis under a hard abort at the
 * budget. A lane that trips that abort is `over_budget` — not an error, not
 * down, just not usable for speech — and the ladder moves on.
 *
 * INT-294 makes the budget cover BOTH legs rather than the synthesis alone.
 * A lane whose /health hangs used to cost the health cap and then start the
 * budget afresh, so one lane could hold the walk for `timeoutMs + budgetMs`;
 * that is how a host in app.json which answers nothing cost 1505 ms in front
 * of a Freya that was answering in 798 ms. Admitting a lane is one turn's
 * worth of work in total, or the lane is not admissible.
 */
export async function measureLane(
  candidate: TtsLaneBase,
  {
    timeoutMs = HEALTH_TIMEOUT_MS,
    budgetMs = ADMISSION_BUDGET_MS,
    fetchImpl = fetch,
    now = Date.now,
    signal,
  }: LaneProbeOptions = {},
): Promise<LaneMeasurement> {
  const measured = (verdict: LaneVerdict, ms: number | null): LaneMeasurement => ({
    id: candidate.id,
    base: candidate.base,
    ms,
    verdict,
  });
  const started = now();
  const remaining = () => budgetMs - (now() - started);

  const healthController = new AbortController();
  const stopHealth = () => healthController.abort();
  signal?.addEventListener("abort", stopHealth);
  const healthTimer = setTimeout(stopHealth, Math.min(timeoutMs, remaining()));
  try {
    const res = await fetchImpl(`${candidate.base}/health`, { signal: healthController.signal });
    if (!res.ok) {
      return measured("unhealthy", null);
    }
  } catch {
    // Refused, DNS, or silent past the cap. None of those is the daemon
    // answering, so none of them is a verdict about the daemon.
    return measured(signal?.aborted === true ? "aborted" : "unreachable", null);
  } finally {
    clearTimeout(healthTimer);
    signal?.removeEventListener("abort", stopHealth);
  }

  const spokenFrom = now();
  try {
    const bytes = await synthesizeOnLane(candidate, LANE_PROBE_TEXT, {
      fetchImpl,
      timeoutMs: Math.max(0, remaining()),
      signal,
    });
    const ms = now() - spokenFrom;
    if (bytes.length === 0) {
      return measured("silent", ms);
    }
    return measured(now() - started > budgetMs ? "over_budget" : "ok", ms);
  } catch (error) {
    const ms = now() - spokenFrom;
    if (signal?.aborted === true) {
      return measured("aborted", ms);
    }
    if (error instanceof Error && error.message === "tts_empty_clip") {
      return measured("silent", ms);
    }
    // An abort is the budget expiring; anything else is the daemon saying no.
    const aborted = error instanceof Error && error.name === "AbortError";
    return measured(aborted || now() - started >= budgetMs ? "over_budget" : "error", ms);
  }
}

export interface LaneSelection {
  readonly lane: TtsLaneBase;
  /** What the winning lane measured. */
  readonly ms: number;
  /**
   * Every lane that ANSWERED, in ladder order. Since INT-294 made the walk a
   * race, a lower-ranked lane can answer before the winner does, so the
   * winner is no longer necessarily last; a lane whose probe was abandoned
   * once the winner was known is absent rather than recorded as a failure.
   */
  readonly measurements: readonly LaneMeasurement[];
}

/**
 * The best lane the ladder can offer, inside ONE admission budget.
 *
 * Ladder order IS the quality order (files/03 §4.9.1: rows 10-11 VoxCPM2,
 * row 12 the low-footprint fallback), so the winner is the FIRST admissible
 * lane in that order — INT-243's intent, unchanged, and overridden only by
 * measurement.
 *
 * What INT-294 changes is how that answer is reached. It used to be a serial
 * walk: probe a lane, wait for its verdict, probe the next. Replaying the
 * owner's configuration, that cost 1721 ms on a VoxCPM2 that is health-green
 * and cannot speak, plus 1505 ms on a configured host the tunnel does not
 * reach, plus 798 ms on the Freya that was going to win from the start —
 * 4024 ms of a 4048 ms clip deadline, spent finding a lane that had been
 * ready the whole time (docs/evidence/INT-294.md).
 *
 * The walk is therefore a RACE resolved by RANK rather than by arrival: every
 * candidate is measured at once, and the winner is the highest-ranked lane
 * that measured `ok` once every lane above it has answered. That keeps
 * quality order exactly — a fast VoxCPM2 still wins, and still settles at its
 * own figure with the losing probes abandoned — while costing the patient one
 * lane's admission for the whole ladder instead of one per (tier, host) pair.
 *
 * A lane that answers nothing costs the budget once, concurrently with the
 * lane that is about to win, rather than in front of it.
 */
export async function selectTtsLane(
  candidates: readonly TtsLaneBase[],
  options: LaneProbeOptions = {},
): Promise<LaneSelection | null> {
  if (candidates.length === 0) {
    return null;
  }
  const { onMeasured, signal, ...probeOptions } = options;
  const controller = new AbortController();
  const stop = () => controller.abort();
  signal?.addEventListener("abort", stop);
  const answered: (LaneMeasurement | null)[] = candidates.map(() => null);
  const settled: boolean[] = candidates.map(() => false);

  try {
    return await new Promise<LaneSelection | null>((resolve) => {
      let decided = false;
      const finish = (selection: LaneSelection | null) => {
        decided = true;
        controller.abort(); // the losers stop the moment the winner is known
        resolve(selection);
      };
      const decide = () => {
        if (decided) {
          return;
        }
        for (let rank = 0; rank < candidates.length; rank += 1) {
          if (!settled[rank]) {
            return; // a better lane may still win; nothing is decided yet
          }
          const measurement = answered[rank];
          if (measurement !== null && measurement.verdict === "ok" && measurement.ms !== null) {
            finish({
              lane: candidates[rank],
              ms: measurement.ms,
              measurements: answered.filter((m): m is LaneMeasurement => m !== null),
            });
            return;
          }
        }
        finish(null);
      };
      candidates.forEach((candidate, rank) => {
        void measureLane(candidate, { ...probeOptions, signal: controller.signal }).then(
          (measurement) => {
            settled[rank] = true;
            if (measurement.verdict !== "aborted") {
              answered[rank] = measurement;
              onMeasured?.(measurement);
            }
            decide();
          },
        );
      });
    });
  } finally {
    signal?.removeEventListener("abort", stop);
  }
}

/**
 * The session's lane, chosen once, re-chosen on failure, and never re-derived
 * from scratch.
 *
 * Probing costs a synthesis, so it happens at session start and not per turn;
 * but a choice cached forever is how a lane that dies at turn nine takes the
 * rest of the visit with it. `invalidate()` is the seam:
 * `synthesizeWithFallback` calls it the moment a synthesis fails, the next
 * `current()` re-probes, and the wedged tier demotes itself because its own
 * probe now trips the budget.
 *
 * INT-294 gives the selector the one memory it was missing. A host that
 * answers NOTHING — the walkthrough's `172.20.10.3`, in app.json and behind a
 * tunnel that binds loopback only — used to cost the full health cap on every
 * walk, forever, to learn the same thing. It is quarantined for the session
 * after it says nothing once. Two limits keep that honest: only a
 * transport-level silence quarantines (a daemon answering 503 says nothing
 * about its neighbours on the same box), and the LAST reachable host is never
 * quarantined, so a whole-network blip cannot leave the session permanently
 * voiceless.
 */
export interface TtsLaneSelector {
  /** The session's lane; throws `tts_unreachable` when none can speak. */
  current(): Promise<TtsLaneBase>;
  /** Drop the cached choice; the next `current()` re-probes. */
  invalidate(): void;
  /** What the last selection measured — for the dev diagnostic. */
  lastMeasurements(): readonly LaneMeasurement[];
  /** How many (tier, host) pairs the ladder can still offer. */
  candidateCount(): number;
}

export function createTtsLaneSelector(
  candidatesFor: () => readonly TtsLaneBase[],
  options: LaneProbeOptions = {},
): TtsLaneSelector {
  let inFlight: Promise<TtsLaneBase> | null = null;
  let measurements: readonly LaneMeasurement[] = [];
  const silentHosts = new Set<string>();
  const admissible = () =>
    candidatesFor().filter((candidate) => !silentHosts.has(laneHost(candidate.base)));
  const quarantine = (measurement: LaneMeasurement) => {
    if (measurement.verdict !== "unreachable") {
      return;
    }
    const host = laneHost(measurement.base);
    const survivors = admissible().filter((candidate) => laneHost(candidate.base) !== host);
    if (survivors.length > 0) {
      silentHosts.add(host);
    }
  };
  return {
    current() {
      // Concurrent callers share one probe: the session pre-warm fires every
      // question at mount and would otherwise probe the ladder N times.
      if (inFlight === null) {
        const probe: Promise<TtsLaneBase> = (async () => {
          const chosen = await selectTtsLane(admissible(), {
            ...options,
            onMeasured: (measurement) => {
              quarantine(measurement);
              options.onMeasured?.(measurement);
            },
          });
          if (chosen === null) {
            measurements = [];
            throw new Error("tts_unreachable");
          }
          measurements = chosen.measurements;
          return chosen.lane;
        })().catch((error: unknown) => {
          // A failed probe is retried, never cached — but only clear the
          // slot if it is still ours. An invalidate() and a fresh probe can
          // both land while this one is still unwinding, and evicting that
          // newer probe would cost the session an extra ladder walk.
          if (inFlight === probe) {
            inFlight = null;
          }
          throw error;
        });
        inFlight = probe;
      }
      return inFlight;
    },
    invalidate() {
      inFlight = null;
    },
    lastMeasurements() {
      return measurements;
    },
    candidateCount() {
      return admissible().length;
    },
  };
}

/**
 * Verdicts on the TEXT rather than on the lane. Retrying these elsewhere
 * would turn invariant 22's guard into a lane-shaped loophole — files/03
 * §4.9.6 disables the daemons' own normalisers precisely so that this guard
 * is the one that matters, and a fallback must not be a second opinion on it.
 */
const TEXT_SIDE_FAILURES = new Set(["tts_numeral_blocked", "tts_empty_text"]);

/**
 * Synthesize on the session's lane, degrading to the next tier rather than
 * to a spinner.
 *
 * One slow lane must cost a worse voice, not a dead turn. On any lane-side
 * failure — the request cap tripping, a non-2xx, an empty body — the
 * selection is invalidated and the next `current()` re-probes, which is what
 * moves the session onto Freya. Text-side failures are rethrown at once.
 */
export async function synthesizeWithFallback(
  selector: TtsLaneSelector,
  text: string,
  options: SynthesizeOptions = {},
): Promise<Uint8Array> {
  assertSpeakableTr(text); // before any lane is even asked for
  const tried = new Set<string>();
  let lastError: unknown;
  const attempts = Math.max(1, selector.candidateCount());
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const lane = await selector.current();
    if (tried.has(lane.base)) {
      break; // the re-probe handed back a lane this call already failed on
    }
    tried.add(lane.base);
    try {
      return await synthesizeOnLane(lane, text, options);
    } catch (error) {
      if (error instanceof Error && TEXT_SIDE_FAILURES.has(error.message)) {
        throw error;
      }
      lastError = error;
      selector.invalidate();
    }
  }
  throw lastError ?? new Error("tts_unavailable");
}

/**
 * POST /synthesize on a resolved lane. Identical wire contract on both tiers
 * — `{"text": ...}` in, WAV bytes out — which is what makes the fallback a
 * swap rather than a rewrite.
 */
export async function synthesizeOnLane(
  lane: TtsLaneBase,
  text: string,
  options: SynthesizeOptions = {},
): Promise<Uint8Array> {
  assertSpeakableTr(text); // invariant 22 — before any network call, every tier
  const { fetchImpl = fetch, timeoutMs = SYNTHESIZE_TIMEOUT_MS, signal } = options;
  const controller = new AbortController();
  const stop = () => controller.abort();
  signal?.addEventListener("abort", stop);
  const timer = setTimeout(stop, timeoutMs);
  try {
    const res = await fetchImpl(`${lane.base}/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error("tts_unavailable");
    }
    const bytes = new Uint8Array(await res.arrayBuffer());
    if (bytes.length === 0) {
      throw new Error("tts_empty_clip");
    }
    return bytes;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", stop);
  }
}
