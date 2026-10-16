/** The wiring (INT-145): one launch is one session; a crash moves the series. */
import { describe, expect, it, vi } from "vitest";

import { createTelemetryRuntime } from "./runtime";
import type { CrashTransport } from "./client";
import type { TelemetryIdentity } from "./scrub";

const IDENTITY: TelemetryIdentity = {
  appVersion: "0.1.0",
  buildId: "eas-1841",
  sbomDigest: `sha256:${"ef".repeat(32)}`,
  platform: "ios",
  osVersion: "18.4",
  deviceModel: "iPhone15,2",
  environment: "dev",
  releaseChannel: "preview",
  tenantId: "acibadem-maslak",
};

function runtime(dsn: string | null = null) {
  const emit = vi.fn();
  const send = vi.fn(async () => ({ ok: true }));
  const transport: CrashTransport = { send };
  return {
    emit,
    send,
    it: createTelemetryRuntime({
      dsn,
      identity: IDENTITY,
      transport,
      metricSink: { emit },
      now: () => 1_772_000_000_000,
    }),
  };
}

describe("createTelemetryRuntime · the dialogue lane counter (INT-440)", () => {
  it("emits one client.dialogue_tts_lane sample per synthesized clip", () => {
    const { it: rt, emit } = runtime();
    rt.noteTtsLane({ lane: "george" });
    rt.noteTtsLane({ lane: "self_hosted", georgeMiss: "not_mounted" });
    expect(emit.mock.calls.map((call) => call[0])).toEqual([
      { metricId: "client.dialogue_tts_lane", value: 1, lane: "george" },
      {
        metricId: "client.dialogue_tts_lane",
        value: 1,
        lane: "self_hosted",
        georgeMiss: "not_mounted",
      },
    ]);
  });
});

describe("createTelemetryRuntime", () => {
  it("counts the launch as one session, crash-free until told otherwise", () => {
    const { it: rt } = runtime();
    expect(rt.state()).toEqual({ sessions: 1, crashes: 0, stalls: 0, coldStartMs: [] });
  });

  it("a cold-start reading emits crash-free share, p95 and the stall rate", () => {
    const { it: rt, emit } = runtime();
    rt.noteColdStart(1830);
    expect(emit.mock.calls.map((call) => call[0])).toEqual([
      { metricId: "client.crash_free_sessions", value: 1 },
      { metricId: "client.cold_start_p95_ms", value: 1830 },
      { metricId: "client.anr_rate", value: 0 },
    ]);
  });

  it("a crash moves the crash-free series and posts a scrubbed report", async () => {
    const { it: rt, emit, send } = runtime("http://f00d@127.0.0.1:8010/7");
    await rt.noteCrash({ errorCode: "dialogue_stream_failed" });
    expect(rt.state().crashes).toBe(1);
    expect(emit).toHaveBeenCalledWith({ metricId: "client.crash_free_sessions", value: 0 });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("with no DSN the counters still move but nothing is posted", async () => {
    const { it: rt, emit, send } = runtime(null);
    expect(rt.crash.status()).toEqual({ active: false, reason: "not_configured" });
    await rt.noteCrash({ errorCode: "dialogue_stream_failed" });
    expect(send).not.toHaveBeenCalled();
    expect(emit).toHaveBeenCalledWith({ metricId: "client.crash_free_sessions", value: 0 });
  });

  it("a previous launch found unclosed counts as one more crashed session", () => {
    const { it: rt } = runtime();
    rt.recordPreviousLaunchCrashed();
    rt.flush();
    expect(rt.state()).toEqual({ sessions: 2, crashes: 1, stalls: 0, coldStartMs: [] });
  });

  it("stalls accumulate without emitting until the next flush", () => {
    const { it: rt, emit } = runtime();
    rt.noteStall();
    expect(emit).not.toHaveBeenCalled();
    rt.flush();
    expect(emit).toHaveBeenCalledWith({ metricId: "client.anr_rate", value: 1 });
  });
});
