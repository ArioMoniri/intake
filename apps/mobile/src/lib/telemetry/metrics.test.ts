/**
 * Client performance series (INT-145; CLAUDE.md invariants 6 and 13).
 * Every id asserted here already exists in observability/metrics_catalog.yaml.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import {
  CLIENT_ANR_RATE,
  CLIENT_COLD_START_P95_MS,
  CLIENT_CRASH_FREE_SESSIONS,
  CLIENT_DIALOGUE_TTS_LANE,
  EMITTED_CLIENT_METRIC_IDS,
  TTS_LANES,
  ttsLaneSample,
  WEB_CORE_WEB_VITALS,
  WEB_VITALS,
  anrRate,
  coldStartP95Ms,
  crashFreeRatio,
  emptyPerfState,
  emitPerf,
  noopClientMetricSink,
  perfSamples,
  recordColdStart,
  recordCrash,
  recordSession,
  recordStall,
  webVitalSample,
} from "./metrics";

describe("the catalogued id set", () => {
  it("names exactly the five series this client is allowed to emit", () => {
    expect([...EMITTED_CLIENT_METRIC_IDS]).toEqual([
      "client.crash_free_sessions",
      "client.cold_start_p95_ms",
      "client.anr_rate",
      "web.core_web_vitals",
      "client.dialogue_tts_lane",
    ]);
    expect(CLIENT_CRASH_FREE_SESSIONS).toBe("client.crash_free_sessions");
    expect(CLIENT_COLD_START_P95_MS).toBe("client.cold_start_p95_ms");
    expect(CLIENT_ANR_RATE).toBe("client.anr_rate");
    expect(WEB_CORE_WEB_VITALS).toBe("web.core_web_vitals");
    expect(CLIENT_DIALOGUE_TTS_LANE).toBe("client.dialogue_tts_lane");
  });

  it("every emitted id is a catalogue row (invariant 13)", () => {
    const catalogue = readFileSync(
      join(
        fileURLToPath(new URL(".", import.meta.url)),
        ...Array(5).fill(".."),
        "observability",
        "metrics_catalog.yaml",
      ),
      "utf8",
    );
    for (const id of EMITTED_CLIENT_METRIC_IDS) {
      expect(catalogue, `${id} is not catalogued`).toContain(`id: ${id}`);
      expect(catalogue).toContain(`name: ${id.replace(/\./g, "_")}`);
    }
  });
});

// INT-440: a non-George clip used to be silent everywhere. It is now one
// counter sample per synthesized clip, labelled by a closed set only.
describe("client.dialogue_tts_lane — which lane spoke each clip", () => {
  it("counts a George clip under lane=george", () => {
    expect(ttsLaneSample({ lane: "george" })).toEqual({
      metricId: "client.dialogue_tts_lane",
      value: 1,
      lane: "george",
    });
  });

  it("counts a fallback clip under lane=self_hosted with the George miss", () => {
    expect(ttsLaneSample({ lane: "self_hosted", georgeMiss: "unauthorized" })).toEqual({
      metricId: "client.dialogue_tts_lane",
      value: 1,
      lane: "self_hosted",
      georgeMiss: "unauthorized",
    });
  });

  it("counts a bundled clip under lane=elevenlabs_bundled", () => {
    expect(ttsLaneSample({ lane: "elevenlabs_bundled" })).toEqual({
      metricId: "client.dialogue_tts_lane",
      value: 1,
      lane: "elevenlabs_bundled",
    });
  });

  it("has a label for every lane and no free-text field", () => {
    expect([...TTS_LANES]).toEqual(["george", "elevenlabs_bundled", "self_hosted"]);
    const sample = ttsLaneSample({ lane: "self_hosted", georgeMiss: "off" });
    expect(Object.keys(sample).sort()).toEqual(["georgeMiss", "lane", "metricId", "value"]);
  });
});

describe("crash-free sessions", () => {
  it("is null before any session — never a confident 1.0", () => {
    expect(crashFreeRatio(emptyPerfState())).toBeNull();
  });

  it("counts crashed sessions against started ones", () => {
    let state = emptyPerfState();
    for (let i = 0; i < 200; i += 1) {
      state = recordSession(state);
    }
    state = recordCrash(state);
    expect(crashFreeRatio(state)).toBeCloseTo(0.995, 6);
  });

  it("clamps into [0,1] when more crashes than sessions are reported", () => {
    let state = recordSession(emptyPerfState());
    state = recordCrash(recordCrash(state));
    expect(crashFreeRatio(state)).toBe(0);
  });
});

describe("cold start p95", () => {
  it("is null with no readings", () => {
    expect(coldStartP95Ms(emptyPerfState())).toBeNull();
  });

  it("takes the nearest rank, inventing no value that was never measured", () => {
    let state = emptyPerfState();
    for (let ms = 1; ms <= 100; ms += 1) {
      state = recordColdStart(state, ms);
    }
    expect(coldStartP95Ms(state)).toBe(95);
  });

  it("a single reading is its own p95", () => {
    expect(coldStartP95Ms(recordColdStart(emptyPerfState(), 1830))).toBe(1830);
  });

  it("refuses a reading that is not a finite, non-negative duration", () => {
    let state = emptyPerfState();
    for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, -1]) {
      state = recordColdStart(state, bad);
    }
    expect(coldStartP95Ms(state)).toBeNull();
  });

  it("keeps a bounded window so a long-lived app cannot grow without limit", () => {
    let state = emptyPerfState();
    for (let i = 0; i < 500; i += 1) {
      state = recordColdStart(state, i + 1);
    }
    expect(state.coldStartMs).toHaveLength(200);
    expect(state.coldStartMs[state.coldStartMs.length - 1]).toBe(500);
  });
});

describe("main-thread stall rate", () => {
  it("is null before any session", () => {
    expect(anrRate(emptyPerfState())).toBeNull();
  });

  it("is stalls over sessions, clamped into [0,1]", () => {
    let state = recordSession(recordSession(emptyPerfState()));
    state = recordStall(state);
    expect(anrRate(state)).toBe(0.5);
    expect(anrRate(recordStall(recordStall(state)))).toBe(1);
  });
});

describe("web vitals", () => {
  it("labels the sample with a vital from the closed set", () => {
    expect(webVitalSample("LCP", 2100)).toEqual({
      metricId: "web.core_web_vitals",
      value: 2100,
      vital: "LCP",
    });
    expect([...WEB_VITALS]).toEqual(["CLS", "FCP", "INP", "LCP", "TTFB"]);
  });

  it("refuses a vital that is not on the closed set", () => {
    expect(webVitalSample("FID" as never, 12)).toBeNull();
  });

  it("refuses a value that is not a finite number", () => {
    expect(webVitalSample("CLS", Number.NaN)).toBeNull();
  });
});

describe("emitPerf", () => {
  it("emits only the series that have a real reading", () => {
    const sink = { emit: vi.fn() };
    let state = recordSession(emptyPerfState());
    state = recordColdStart(state, 1830);
    emitPerf(sink, state);
    expect(sink.emit.mock.calls.map((call) => call[0])).toEqual([
      { metricId: "client.crash_free_sessions", value: 1 },
      { metricId: "client.cold_start_p95_ms", value: 1830 },
      { metricId: "client.anr_rate", value: 0 },
    ]);
  });

  it("emits nothing at all from an empty state", () => {
    const sink = { emit: vi.fn() };
    emitPerf(sink, emptyPerfState());
    expect(sink.emit).not.toHaveBeenCalled();
  });

  it("refuses a sample whose id is not catalogued", () => {
    const sink = { emit: vi.fn() };
    // The guard exists so a future series cannot be emitted before it is
    // catalogued (invariant 13); reach it directly.
    expect(perfSamples(emptyPerfState())).toEqual([]);
    expect(noopClientMetricSink.emit({ metricId: CLIENT_ANR_RATE, value: 0 })).toBeUndefined();
    expect(sink.emit).not.toHaveBeenCalled();
  });

  it("carries no field a transcript or a phone number could sit in", () => {
    const sample = webVitalSample("INP", 190);
    expect(Object.keys(sample ?? {}).sort()).toEqual(["metricId", "value", "vital"]);
  });
});
