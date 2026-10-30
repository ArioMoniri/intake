/**
 * INT-559 — the dev ASR client takes a segment from memory and sends bytes.
 * It never sees a path, and whatever it was handed is zero by the time it
 * returns, whichever way the request went.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { SEGMENT_TIMEOUT_MS, TRANSCRIBE_PATH, transcribeSegmentAt } from "./asrClient";
import type { PcmSegment } from "./types";

interface Call {
  url: string;
  method: string | undefined;
  headers: Record<string, string>;
  body: Uint8Array;
}

function fakeFetch(
  respond: (call: Call) => { ok: boolean; status: number; json: () => Promise<unknown> },
) {
  const calls: Call[] = [];
  const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const body = init?.body;
    expect(body).toBeInstanceOf(Uint8Array);
    const call: Call = {
      url: String(input),
      method: init?.method,
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: Uint8Array.from(body as Uint8Array),
    };
    calls.push(call);
    return respond(call) as unknown as Response;
  }) as typeof fetch;
  return { calls, fetchImpl };
}

function segment(): PcmSegment {
  return { samples: new Int16Array([10, -10, 300]), sampleRate: 16_000, channels: 1 };
}

const BASE = "http://127.0.0.1:8802";

afterEach(() => {
  vi.useRealTimers();
});

describe("transcribeSegmentAt", () => {
  it("POSTs the envelope bytes to /transcribe and returns the trimmed text", async () => {
    const { calls, fetchImpl } = fakeFetch(() => ({
      ok: true,
      status: 200,
      json: async () => ({ text: "  göğsümde baskı var \n" }),
    }));
    const text = await transcribeSegmentAt(BASE, segment(), { fetchImpl });
    expect(text).toBe("göğsümde baskı var");
    expect(TRANSCRIBE_PATH).toBe("/transcribe");
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(`${BASE}/transcribe`);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].headers["Content-Type"]).toBe("application/octet-stream");
    expect(calls[0].headers["X-Intake-Audio"]).toBe("pcm_s16le;rate=16000;channels=1");
    expect(calls[0].body.byteLength).toBe(44 + 6);
    expect(String.fromCharCode(...calls[0].body.subarray(0, 4))).toBe("RIFF");
    expect(Array.from(calls[0].body.subarray(44))).toEqual([10, 0, 0xf6, 0xff, 0x2c, 0x01]);
  });

  it("zeroes the segment it was handed once the request has settled", async () => {
    const { fetchImpl } = fakeFetch(() => ({
      ok: true,
      status: 200,
      json: async () => ({ text: "x" }),
    }));
    const own = segment();
    await transcribeSegmentAt(BASE, own, { fetchImpl });
    expect(Array.from(own.samples)).toEqual([0, 0, 0]);
  });

  it("zeroes the segment on failure too", async () => {
    const { fetchImpl } = fakeFetch(() => ({ ok: false, status: 503, json: async () => ({}) }));
    const own = segment();
    await expect(transcribeSegmentAt(BASE, own, { fetchImpl })).rejects.toThrow("asr_unavailable");
    expect(Array.from(own.samples)).toEqual([0, 0, 0]);
  });

  it("reads a missing text as empty", async () => {
    const { fetchImpl } = fakeFetch(() => ({ ok: true, status: 200, json: async () => ({}) }));
    expect(await transcribeSegmentAt(BASE, segment(), { fetchImpl })).toBe("");
  });

  it("a body that is not JSON is an invalid response", async () => {
    const { fetchImpl } = fakeFetch(() => ({
      ok: true,
      status: 200,
      json: async () => Promise.reject(new SyntaxError("nope")),
    }));
    await expect(transcribeSegmentAt(BASE, segment(), { fetchImpl })).rejects.toThrow(
      "asr_invalid_response",
    );
  });

  it("a transport rejection is unreachable", async () => {
    const fetchImpl = (async () =>
      Promise.reject(new TypeError("Network request failed"))) as typeof fetch;
    const own = segment();
    await expect(transcribeSegmentAt(BASE, own, { fetchImpl })).rejects.toThrow("asr_unreachable");
    expect(Array.from(own.samples)).toEqual([0, 0, 0]);
  });

  it("gives up on a hung daemon after the segment timeout", async () => {
    vi.useFakeTimers();
    expect(SEGMENT_TIMEOUT_MS).toBe(90_000);
    const fetchImpl = ((_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new Error("aborted")));
      })) as typeof fetch;
    const pending = transcribeSegmentAt(BASE, segment(), { fetchImpl, timeoutMs: 5_000 });
    const settled = expect(pending).rejects.toThrow("asr_timeout");
    await vi.advanceTimersByTimeAsync(5_000);
    await settled;
  });

  it("an already-aborted signal sends nothing", async () => {
    const { calls, fetchImpl } = fakeFetch(() => ({
      ok: true,
      status: 200,
      json: async () => ({}),
    }));
    const controller = new AbortController();
    controller.abort();
    const own = segment();
    await expect(
      transcribeSegmentAt(BASE, own, { fetchImpl, signal: controller.signal }),
    ).rejects.toThrow("asr_aborted");
    expect(calls).toEqual([]);
    expect(Array.from(own.samples)).toEqual([0, 0, 0]);
  });
});
