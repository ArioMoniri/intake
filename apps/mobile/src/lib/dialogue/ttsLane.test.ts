/**
 * INT-243: the dev TTS lane is an ORDERED list of tiers, not one hardcoded
 * port. VoxCPM2 (files/03 §4.9.1 rows 10-11) serves on 8805; FreyaTTS (row
 * 12) stays on 8803 as the whole-session fallback, so a failed VoxCPM2
 * rollout costs nothing. The order and the ports come from config.
 *
 * INT-249: and the tier must prove it can SPEAK, not merely answer. Measured
 * on the host with both lanes tunnelled and healthy (docs/evidence/INT-249.md,
 * 29 Aug 2026): 8805 timed out at 8.0 s returning 0 bytes while 8803 answered
 * 200 with 276,524 bytes in 1.21 s. Both passed /health. Health-only selection
 * therefore chose the lane that cannot meet a turn budget, and the patient
 * watched "Soru hazırlanıyor…" for thirty seconds before the dialogue tore
 * itself down.
 *
 * The fake below reproduces that exact shape — /health answers at once, then
 * /synthesize hangs on the fake clock and honours the abort signal. A mocked
 * promise that resolves instantly cannot express this defect, so it is not
 * used here.
 *
 * Invariant 22 rides along: whichever tier answers, the digit guard is the
 * same one, it throws before any request leaves the app, and a fallback must
 * never be a second chance for text the guard already refused.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SYNTHESIZE_TIMEOUT_MS, TURN_ROUND_TRIP_BUDGET_MS } from "./tts";
import {
  DEFAULT_TTS_LANES,
  LANE_PROBE_TEXT,
  createTtsLaneSelector,
  laneCandidates,
  measureLane,
  parseTtsLanes,
  selectTtsLane,
  synthesizeOnLane,
  synthesizeWithFallback,
  type TtsLaneBase,
} from "./ttsLane";

const VOX: TtsLaneBase = { id: "voxcpm2", base: "http://127.0.0.1:8805" };
const FREYA: TtsLaneBase = { id: "freya", base: "http://127.0.0.1:8803" };
const LADDER = [VOX, FREYA];

const WAV = new Uint8Array([82, 73, 70, 70, 1, 2, 3, 4]);

interface LaneBehaviour {
  /** Does GET /health answer 2xx? */
  readonly healthy: boolean;
  /** Fake-clock milliseconds POST /synthesize takes to answer. */
  readonly synthesizeMs: number;
  /** Bytes the synthesis answers with; empty means the lane went silent. */
  readonly bytes?: Uint8Array;
  /** Answer /synthesize with this non-2xx status instead. */
  readonly synthesizeStatus?: number;
}

/**
 * A controllable fake of the two dev TTS daemons, driven by the fake clock.
 * `/health` resolves in the current tick; `/synthesize` resolves only after
 * `synthesizeMs` have been advanced, and rejects with an AbortError the
 * moment the caller's own timeout fires. A host not in the map refuses the
 * connection, the way a dead tunnel does.
 */
function laneServer(spec: Record<string, LaneBehaviour>): {
  fetchImpl: typeof fetch;
  calls: string[];
} {
  const calls: string[] = [];
  const fetchImpl = (async (url: RequestInfo | URL, init?: RequestInit) => {
    const target = String(url);
    calls.push(target);
    const base = Object.keys(spec).find((candidate) => target.startsWith(`${candidate}/`));
    if (base === undefined) {
      throw new Error("ECONNREFUSED");
    }
    const lane = spec[base];
    if (target.endsWith("/health")) {
      return (lane.healthy ? { ok: true, status: 200 } : { ok: false, status: 503 }) as Response;
    }
    return new Promise<Response>((resolve, reject) => {
      const timer = setTimeout(() => {
        const status = lane.synthesizeStatus ?? 200;
        const bytes = lane.bytes ?? WAV;
        resolve({
          ok: status >= 200 && status < 300,
          status,
          arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteLength),
        } as Response);
      }, lane.synthesizeMs);
      init?.signal?.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      });
    });
  }) as typeof fetch;
  return { fetchImpl, calls };
}

/**
 * The measured numbers, so the fixtures are the incident and not a guess
 * (docs/evidence/INT-249.md, one-word probe against the live daemons).
 */
const VOX_ON_CPU_MS = 3_990; // 8805, CPU: 3.99 s for one word — over budget
const FREYA_MS = 1_030; // 8803: 1.03 s for the same word — inside budget
const VOX_ON_GPU_MS = 140; // files/03 §4.9.1 row 11, TTFT 0.14 s on a 4090

/** Both lanes healthy; VoxCPM2 wedged on CPU exactly as measured. */
const WEDGED_VOX: Record<string, LaneBehaviour> = {
  [VOX.base]: { healthy: true, synthesizeMs: VOX_ON_CPU_MS },
  [FREYA.base]: { healthy: true, synthesizeMs: FREYA_MS },
};

/** Both lanes healthy and both inside the budget — the ladder's happy path. */
const FAST_BOTH: Record<string, LaneBehaviour> = {
  [VOX.base]: { healthy: true, synthesizeMs: VOX_ON_GPU_MS },
  [FREYA.base]: { healthy: true, synthesizeMs: FREYA_MS },
};

/**
 * Runs a lane operation to completion on the fake clock, recording the
 * instant it actually settled. Reading `Date.now()` after the advance would
 * report the whole window rather than the wait, which is the difference
 * between "the lane gave up at the budget" and "the lane sat there".
 */
async function settleTimed<T>(
  work: Promise<T>,
  ms = 60_000,
): Promise<{ value: T; elapsedMs: number }> {
  const started = Date.now();
  let finishedAt: number | null = null;
  const stamp = () => {
    finishedAt ??= Date.now();
  };
  const result = work.then(
    (value) => {
      stamp();
      return { ok: true as const, value };
    },
    (error: unknown) => {
      stamp();
      return { ok: false as const, error };
    },
  );
  await vi.advanceTimersByTimeAsync(ms);
  const settled = await result;
  const elapsedMs = (finishedAt ?? Date.now()) - started;
  if (!settled.ok) {
    throw settled.error;
  }
  return { value: settled.value, elapsedMs };
}

/** Runs a lane operation to completion on the fake clock. */
async function settle<T>(work: Promise<T>, ms = 60_000): Promise<T> {
  return (await settleTimed(work, ms)).value;
}

describe("DEFAULT_TTS_LANES", () => {
  it("puts VoxCPM2 (8805) first and keeps Freya (8803) as the fallback", () => {
    expect(DEFAULT_TTS_LANES.map((l) => [l.id, l.port])).toEqual([
      ["voxcpm2", 8805],
      ["freya", 8803],
    ]);
  });
});

describe("parseTtsLanes (config, not hardcode)", () => {
  it("takes an app.json list and preserves its order", () => {
    expect(
      parseTtsLanes([
        { id: "freya", port: 8803 },
        { id: "voxcpm2", port: 8805 },
      ]),
    ).toEqual([
      { id: "freya", port: 8803 },
      { id: "voxcpm2", port: 8805 },
    ]);
  });

  it("falls back to the built-in order when unset or empty", () => {
    expect(parseTtsLanes(undefined)).toEqual(DEFAULT_TTS_LANES);
    expect(parseTtsLanes([])).toEqual(DEFAULT_TTS_LANES);
  });

  it("rejects malformed entries rather than inventing a port", () => {
    expect(() => parseTtsLanes([{ id: "voxcpm2" }])).toThrow();
    expect(() => parseTtsLanes([{ id: "", port: 8805 }])).toThrow();
    expect(() => parseTtsLanes([{ id: "voxcpm2", port: 0 }])).toThrow();
    expect(() => parseTtsLanes("8805")).toThrow();
  });
});

describe("laneCandidates", () => {
  it("walks every lane in order, each across its hosts", () => {
    expect(laneCandidates(undefined, ["127.0.0.1", "10.0.0.9"], DEFAULT_TTS_LANES)).toEqual([
      { id: "voxcpm2", base: "http://127.0.0.1:8805" },
      { id: "voxcpm2", base: "http://10.0.0.9:8805" },
      { id: "freya", base: "http://127.0.0.1:8803" },
      { id: "freya", base: "http://10.0.0.9:8803" },
    ]);
  });
});

describe("the budget comes from the blueprint, not from this file", () => {
  it("is files/03 §4.4's stated round-trip for the one production profile", () => {
    // §4.4, `residency_tr` row, under the column "expected round-trip p50
    // (end of speech → first agent audio)": "p95 ≈ 1684–2364 ms". §4.5 fixes
    // the definition: last patient speech sample → first agent audio sample
    // played. On the dev clip path that round-trip IS the synthesis.
    expect(TURN_ROUND_TRIP_BUDGET_MS).toBe(1684);
  });

  it("caps one live request at the other end of the same stated band", () => {
    // Admission takes the best of the band, a request already in flight is
    // allowed the worst of it — both ends the blueprint's, neither invented.
    expect(SYNTHESIZE_TIMEOUT_MS).toBe(2364);
    expect(SYNTHESIZE_TIMEOUT_MS).toBeGreaterThan(TURN_ROUND_TRIP_BUDGET_MS);
  });

  it("probes with numeral-free Turkish — invariant 22 covers the probe too", () => {
    expect(LANE_PROBE_TEXT.trim().length).toBeGreaterThan(0);
    expect(LANE_PROBE_TEXT).not.toMatch(/\p{Nd}/u);
  });
});

describe("measureLane (a lane must prove it can speak)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("measures a real short synthesis and reports the milliseconds", async () => {
    const { fetchImpl, calls } = laneServer(FAST_BOTH);
    const measured = await settle(measureLane(VOX, { fetchImpl }));
    expect(measured.verdict).toBe("ok");
    expect(measured.ms).toBe(VOX_ON_GPU_MS);
    expect(measured.id).toBe("voxcpm2");
    expect(calls).toEqual(["http://127.0.0.1:8805/health", "http://127.0.0.1:8805/synthesize"]);
  });

  it("fails a lane that answers /health and then hangs — the measured defect", async () => {
    const { fetchImpl } = laneServer(WEDGED_VOX);
    const measured = await settle(measureLane(VOX, { fetchImpl }));
    expect(measured.verdict).toBe("over_budget");
    expect(measured.ms).toBeGreaterThanOrEqual(TURN_ROUND_TRIP_BUDGET_MS);
  });

  it("never waits longer than the budget on a wedged lane", async () => {
    const { fetchImpl } = laneServer(WEDGED_VOX);
    // The lane would have answered at 3.99 s. The probe must not be there to
    // hear it: it gives up at the budget and the ladder moves on.
    const { elapsedMs } = await settleTimed(measureLane(VOX, { fetchImpl }));
    expect(elapsedMs).toBeLessThanOrEqual(TURN_ROUND_TRIP_BUDGET_MS);
  });

  it("does not spend a synthesis on a lane whose /health is down", async () => {
    const { fetchImpl, calls } = laneServer({
      [VOX.base]: { healthy: false, synthesizeMs: 10 },
    });
    const measured = await settle(measureLane(VOX, { fetchImpl }));
    expect(measured.verdict).toBe("unhealthy");
    expect(measured.ms).toBeNull();
    expect(calls).toEqual(["http://127.0.0.1:8805/health"]);
  });

  it("treats an empty body as silence, not as success", async () => {
    const { fetchImpl } = laneServer({
      [VOX.base]: { healthy: true, synthesizeMs: 20, bytes: new Uint8Array([]) },
    });
    expect((await settle(measureLane(VOX, { fetchImpl }))).verdict).toBe("silent");
  });

  it("treats a transport error as down, not as a crash", async () => {
    const { fetchImpl } = laneServer({});
    expect((await settle(measureLane(VOX, { fetchImpl }))).verdict).toBe("unhealthy");
  });

  it("returns a duration and never the probe audio — no clip is kept", async () => {
    const { fetchImpl } = laneServer(FAST_BOTH);
    const measured = await settle(measureLane(VOX, { fetchImpl }));
    expect(Object.keys(measured).sort()).toEqual(["base", "id", "ms", "verdict"]);
  });
});

describe("selectTtsLane (latency-aware, ladder intent preserved)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("skips a healthy-but-slow VoxCPM2 and speaks on Freya instead", async () => {
    const { fetchImpl } = laneServer(WEDGED_VOX);
    const chosen = await settle(selectTtsLane(LADDER, { fetchImpl }));
    expect(chosen?.lane).toEqual(FREYA);
    expect(chosen?.ms).toBe(FREYA_MS);
  });

  it("keeps VoxCPM2 when it is actually fast — quality wins inside budget", async () => {
    const { fetchImpl } = laneServer(FAST_BOTH);
    const chosen = await settle(selectTtsLane(LADDER, { fetchImpl }));
    expect(chosen?.lane).toEqual(VOX);
    expect(chosen?.ms).toBe(VOX_ON_GPU_MS);
  });

  it("stops at the first lane inside budget rather than probing the rest", async () => {
    const { fetchImpl, calls } = laneServer(FAST_BOTH);
    await settle(selectTtsLane(LADDER, { fetchImpl }));
    expect(calls.some((c) => c.startsWith(FREYA.base))).toBe(false);
  });

  it("reports what every probed lane measured, so the choice is explicable", async () => {
    const { fetchImpl } = laneServer(WEDGED_VOX);
    const chosen = await settle(selectTtsLane(LADDER, { fetchImpl }));
    expect(chosen?.measurements.map((m) => [m.id, m.verdict])).toEqual([
      ["voxcpm2", "over_budget"],
      ["freya", "ok"],
    ]);
  });

  it("returns null when no lane can speak inside the budget", async () => {
    const { fetchImpl } = laneServer({
      [VOX.base]: { healthy: true, synthesizeMs: VOX_ON_CPU_MS },
      [FREYA.base]: { healthy: true, synthesizeMs: 9_000 }, // both wedged
    });
    expect(await settle(selectTtsLane(LADDER, { fetchImpl }))).toBeNull();
  });
});

describe("createTtsLaneSelector (one probe per session, re-probe on failure)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("probes once and serves the cached choice for the rest of the session", async () => {
    const { fetchImpl, calls } = laneServer(FAST_BOTH);
    const selector = createTtsLaneSelector(() => LADDER, { fetchImpl });
    expect(await settle(selector.current())).toEqual(VOX);
    const afterFirst = calls.length;
    expect(await settle(selector.current())).toEqual(VOX);
    expect(await settle(selector.current())).toEqual(VOX);
    expect(calls.length).toBe(afterFirst);
  });

  it("shares one in-flight probe between concurrent callers", async () => {
    const { fetchImpl, calls } = laneServer(FAST_BOTH);
    const selector = createTtsLaneSelector(() => LADDER, { fetchImpl });
    const both = Promise.all([selector.current(), selector.current()]);
    expect(await settle(both)).toEqual([VOX, VOX]);
    expect(calls.filter((c) => c.endsWith("/health")).length).toBe(1);
  });

  it("re-probes after invalidate, so a lane that dies mid-session is replaced", async () => {
    const behaviour: Record<string, LaneBehaviour> = {
      [VOX.base]: { healthy: true, synthesizeMs: VOX_ON_GPU_MS },
      [FREYA.base]: { healthy: true, synthesizeMs: FREYA_MS },
    };
    const { fetchImpl } = laneServer(behaviour);
    const selector = createTtsLaneSelector(() => LADDER, { fetchImpl });
    expect(await settle(selector.current())).toEqual(VOX);
    behaviour[VOX.base] = { healthy: true, synthesizeMs: 8_000 }; // VoxCPM2 wedges
    selector.invalidate();
    expect(await settle(selector.current())).toEqual(FREYA);
  });

  it("throws tts_unreachable when the whole ladder fails the budget", async () => {
    const { fetchImpl } = laneServer({
      [VOX.base]: { healthy: true, synthesizeMs: VOX_ON_CPU_MS },
      [FREYA.base]: { healthy: false, synthesizeMs: 10 },
    });
    const selector = createTtsLaneSelector(() => LADDER, { fetchImpl });
    await expect(settle(selector.current())).rejects.toThrow("tts_unreachable");
  });

  it("exposes the last measurements for the dev diagnostic", async () => {
    const { fetchImpl } = laneServer(WEDGED_VOX);
    const selector = createTtsLaneSelector(() => LADDER, { fetchImpl });
    await settle(selector.current());
    expect(selector.lastMeasurements().map((m) => m.verdict)).toEqual(["over_budget", "ok"]);
  });
});

describe("synthesizeWithFallback (one slow lane degrades to a slower voice)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("falls through to Freya when the selected lane hangs mid-session", async () => {
    const behaviour: Record<string, LaneBehaviour> = {
      [VOX.base]: { healthy: true, synthesizeMs: VOX_ON_GPU_MS },
      [FREYA.base]: { healthy: true, synthesizeMs: FREYA_MS },
    };
    const { fetchImpl, calls } = laneServer(behaviour);
    const selector = createTtsLaneSelector(() => LADDER, { fetchImpl });
    expect(await settle(selector.current())).toEqual(VOX);
    // The GPU slice fills and VoxCPM2 wedges after selection.
    behaviour[VOX.base] = { healthy: true, synthesizeMs: 60_000 };
    calls.length = 0;
    const bytes = await settle(synthesizeWithFallback(selector, "Hangi tarafta?", { fetchImpl }));
    expect(bytes).toEqual(WAV);
    expect(calls.some((c) => c === `${FREYA.base}/synthesize`)).toBe(true);
  });

  it("hands the turn back inside the request cap rather than sitting on it", async () => {
    const behaviour: Record<string, LaneBehaviour> = {
      [VOX.base]: { healthy: true, synthesizeMs: VOX_ON_GPU_MS },
      [FREYA.base]: { healthy: true, synthesizeMs: FREYA_MS },
    };
    const { fetchImpl } = laneServer(behaviour);
    const selector = createTtsLaneSelector(() => LADDER, { fetchImpl });
    await settle(selector.current());
    behaviour[VOX.base] = { healthy: true, synthesizeMs: 60_000 };
    // The wedged tier costs one request cap and one re-probe, and the words
    // still arrive. Before INT-249 this was 30 s per sentence and then a
    // dead dialogue.
    const { elapsedMs } = await settleTimed(
      synthesizeWithFallback(selector, "Hangi tarafta?", { fetchImpl }),
    );
    expect(elapsedMs).toBeLessThan(30_000);
    expect(elapsedMs).toBeLessThanOrEqual(
      SYNTHESIZE_TIMEOUT_MS + TURN_ROUND_TRIP_BUDGET_MS * 2 + FREYA_MS,
    );
  });

  it("does not offer a second lane to text the digit guard refused", async () => {
    const { fetchImpl, calls } = laneServer(FAST_BOTH);
    const selector = createTtsLaneSelector(() => LADDER, { fetchImpl });
    await settle(selector.current());
    calls.length = 0;
    await expect(
      settle(synthesizeWithFallback(selector, "15 mg alın", { fetchImpl })),
    ).rejects.toThrow("tts_numeral_blocked");
    expect(calls).toEqual([]);
  });

  it("gives up honestly when no lane can speak", async () => {
    const behaviour: Record<string, LaneBehaviour> = {
      [VOX.base]: { healthy: true, synthesizeMs: VOX_ON_GPU_MS },
      [FREYA.base]: { healthy: true, synthesizeMs: FREYA_MS },
    };
    const { fetchImpl } = laneServer(behaviour);
    const selector = createTtsLaneSelector(() => LADDER, { fetchImpl });
    await settle(selector.current());
    behaviour[VOX.base] = { healthy: true, synthesizeMs: 60_000 };
    behaviour[FREYA.base] = { healthy: true, synthesizeMs: 60_000 };
    await expect(
      settle(synthesizeWithFallback(selector, "Hangi tarafta?", { fetchImpl })),
    ).rejects.toThrow();
  });
});

describe("synthesizeOnLane (invariant 22 holds on every tier)", () => {
  it("throws on a numeral before any request leaves the app", async () => {
    const fetchImpl = vi.fn();
    await expect(synthesizeOnLane(VOX, "15 mg alın", { fetchImpl })).rejects.toThrow(
      "tts_numeral_blocked",
    );
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("throws on a numeral for the fallback tier too", async () => {
    const fetchImpl = vi.fn();
    await expect(synthesizeOnLane(FREYA, "günde ٣ kez", { fetchImpl })).rejects.toThrow(
      "tts_numeral_blocked",
    );
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("posts to /synthesize on the resolved base and returns the bytes", async () => {
    const wav = new Uint8Array([82, 73, 70, 70]);
    let seen: string | undefined;
    let body: string | undefined;
    const fetchImpl = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      seen = String(url);
      body = String(init?.body);
      return { ok: true, arrayBuffer: async () => wav.buffer.slice(0) } as Response;
    });
    const out = await synthesizeOnLane(VOX, "Hangi tarafta?", { fetchImpl });
    expect(out).toEqual(wav);
    expect(seen).toBe("http://127.0.0.1:8805/synthesize");
    expect(body).toBe(JSON.stringify({ text: "Hangi tarafta?" }));
  });

  it("uses the same wire contract on the Freya tier, so fallback is a swap", async () => {
    const wav = new Uint8Array([1, 2, 3]);
    let seen: string | undefined;
    const fetchImpl = vi.fn(async (url: RequestInfo | URL) => {
      seen = String(url);
      return { ok: true, arrayBuffer: async () => wav.buffer.slice(0) } as Response;
    });
    await synthesizeOnLane(FREYA, "Hangi tarafta?", { fetchImpl });
    expect(seen).toBe("http://127.0.0.1:8803/synthesize");
  });

  it("surfaces a non-2xx as tts_unavailable so the caller can drop to typed", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: false, status: 503 }) as Response);
    await expect(synthesizeOnLane(VOX, "Hangi tarafta?", { fetchImpl })).rejects.toThrow(
      "tts_unavailable",
    );
  });
});
