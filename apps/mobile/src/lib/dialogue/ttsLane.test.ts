/**
 * INT-240: the dev TTS lane is an ORDERED list of tiers, not one hardcoded
 * port. VoxCPM2 (files/03 §4.9.1 rows 10-11) serves on 8805; FreyaTTS (row
 * 12) stays on 8803 as the whole-session fallback, so a failed VoxCPM2
 * rollout costs nothing. The order and the ports come from config.
 *
 * Invariant 22 rides along: whichever tier answers, the digit guard is the
 * same one, and it throws before any request leaves the app.
 */
import { describe, expect, it, vi } from "vitest";

import {
  DEFAULT_TTS_LANES,
  laneCandidates,
  parseTtsLanes,
  resolveTtsLane,
  synthesizeOnLane,
} from "./ttsLane";

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

describe("resolveTtsLane (automatic fallback)", () => {
  const health = (up: readonly string[]) =>
    vi.fn(async (url: RequestInfo | URL) =>
      up.some((u) => String(url).startsWith(u))
        ? ({ ok: true } as Response)
        : ({ ok: false, status: 503 } as Response),
    );

  it("prefers VoxCPM2 when 8805 answers, and never probes the fallback", async () => {
    const fetchImpl = health(["http://127.0.0.1:8805", "http://127.0.0.1:8803"]);
    await expect(
      resolveTtsLane(
        [
          { id: "voxcpm2", base: "http://127.0.0.1:8805" },
          { id: "freya", base: "http://127.0.0.1:8803" },
        ],
        { fetchImpl },
      ),
    ).resolves.toEqual({ id: "voxcpm2", base: "http://127.0.0.1:8805" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("falls back to Freya when VoxCPM2 is down", async () => {
    const fetchImpl = health(["http://127.0.0.1:8803"]);
    await expect(
      resolveTtsLane(
        [
          { id: "voxcpm2", base: "http://127.0.0.1:8805" },
          { id: "freya", base: "http://127.0.0.1:8803" },
        ],
        { fetchImpl },
      ),
    ).resolves.toEqual({ id: "freya", base: "http://127.0.0.1:8803" });
  });

  it("returns null when the whole lane is down", async () => {
    const fetchImpl = health([]);
    await expect(
      resolveTtsLane([{ id: "voxcpm2", base: "http://127.0.0.1:8805" }], { fetchImpl }),
    ).resolves.toBeNull();
  });

  it("treats a transport error as down, not as a crash", async () => {
    const fetchImpl = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).startsWith("http://127.0.0.1:8805")) {
        throw new Error("ECONNREFUSED");
      }
      return { ok: true } as Response;
    });
    await expect(
      resolveTtsLane(
        [
          { id: "voxcpm2", base: "http://127.0.0.1:8805" },
          { id: "freya", base: "http://127.0.0.1:8803" },
        ],
        { fetchImpl },
      ),
    ).resolves.toEqual({ id: "freya", base: "http://127.0.0.1:8803" });
  });
});

describe("synthesizeOnLane (invariant 22 holds on every tier)", () => {
  it("throws on a numeral before any request leaves the app", async () => {
    const fetchImpl = vi.fn();
    await expect(
      synthesizeOnLane({ id: "voxcpm2", base: "http://127.0.0.1:8805" }, "15 mg alın", {
        fetchImpl,
      }),
    ).rejects.toThrow("tts_numeral_blocked");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("throws on a numeral for the fallback tier too", async () => {
    const fetchImpl = vi.fn();
    await expect(
      synthesizeOnLane({ id: "freya", base: "http://127.0.0.1:8803" }, "günde ٣ kez", {
        fetchImpl,
      }),
    ).rejects.toThrow("tts_numeral_blocked");
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
    const out = await synthesizeOnLane(
      { id: "voxcpm2", base: "http://127.0.0.1:8805" },
      "Hangi tarafta?",
      { fetchImpl },
    );
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
    await synthesizeOnLane({ id: "freya", base: "http://127.0.0.1:8803" }, "Hangi tarafta?", {
      fetchImpl,
    });
    expect(seen).toBe("http://127.0.0.1:8803/synthesize");
  });

  it("surfaces a non-2xx as tts_unavailable so the caller can drop to typed", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: false, status: 503 }) as Response);
    await expect(
      synthesizeOnLane({ id: "voxcpm2", base: "http://127.0.0.1:8805" }, "Hangi tarafta?", {
        fetchImpl,
      }),
    ).rejects.toThrow("tts_unavailable");
  });
});
