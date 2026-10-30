/**
 * INT-559 — one turn of the microphone, as the dialogue and the voice-note
 * pill both run it: open, hand every segment to the ASR client the moment
 * it exists, and settle the transcript at finish. The stream and the client
 * are ports, so the whole turn runs in node.
 */
import { describe, expect, it } from "vitest";

import { createCaptureTurn, joinTranscripts } from "./turn";
import type { PcmChunk, PcmFormat, PcmSegment, PcmStreamPort } from "./types";

function harness(options: { transcribe?: (segment: PcmSegment) => Promise<string> } = {}) {
  const listeners = new Set<(chunk: PcmChunk) => void>();
  const calls: string[] = [];
  const formats: PcmFormat[] = [];
  const seen: PcmSegment[] = [];
  const port: PcmStreamPort = {
    start: async () => {
      calls.push("start");
    },
    stop: () => {
      calls.push("stop");
    },
    onBuffer: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
  return {
    calls,
    formats,
    seen,
    emit(samples: Int16Array, sampleRate = 1_000) {
      const data = samples.buffer.slice(
        samples.byteOffset,
        samples.byteOffset + samples.byteLength,
      ) as ArrayBuffer;
      for (const listener of listeners) {
        listener({ data, sampleRate, channels: 1 });
      }
    },
    deps: {
      createStream: async (format: PcmFormat) => {
        formats.push(format);
        calls.push("create");
        return port;
      },
      transcribe:
        options.transcribe ??
        (async (segment: PcmSegment) => {
          seen.push({ ...segment, samples: Int16Array.from(segment.samples) });
          return `seg${seen.length}`;
        }),
    },
  };
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

/**
 * A turn whose two awaits — the native stream's creation and its start —
 * each wait until released, so a discard or a finish can land inside either.
 * `started` is recorded when the start settles, so a stop sent before it
 * (which the native stream would lose) is visible in the order of calls.
 */
function gatedHarness() {
  const listeners = new Set<(chunk: PcmChunk) => void>();
  const calls: string[] = [];
  const sent: PcmSegment[] = [];
  let releaseCreate: () => void = () => undefined;
  let releaseStart: () => void = () => undefined;
  const port: PcmStreamPort = {
    start: () => {
      calls.push("start");
      return new Promise<void>((resolve) => {
        releaseStart = () => {
          calls.push("started");
          resolve();
        };
      });
    },
    stop: () => {
      calls.push("stop");
    },
    onBuffer: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
  return {
    calls,
    sent,
    listeners: () => listeners.size,
    /** More than the one-second window, so a live capture would hand a segment to the client. */
    emitPastTheWindow() {
      const data = new Int16Array(1_500).fill(4).buffer as ArrayBuffer;
      for (const listener of listeners) {
        listener({ data, sampleRate: 1_000, channels: 1 });
      }
    },
    releaseCreate: () => releaseCreate(),
    releaseStart: () => releaseStart(),
    deps: {
      createStream: () => {
        calls.push("create");
        return new Promise<PcmStreamPort>((resolve) => {
          releaseCreate = () => resolve(port);
        });
      },
      transcribe: async (segment: PcmSegment) => {
        sent.push(segment);
        return "söz";
      },
      maxSeconds: 1,
    },
  };
}

describe("joinTranscripts", () => {
  it("joins the segment texts in order, dropping empties", () => {
    expect(joinTranscripts(["göğsümde", "", "  baskı var  "])).toBe("göğsümde baskı var");
    expect(joinTranscripts([])).toBe("");
    expect(joinTranscripts(["", "   "])).toBe("");
  });
});

describe("createCaptureTurn", () => {
  it("asks the platform for the capture format and opens", async () => {
    const h = harness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    expect(await turn.open()).toBe(true);
    expect(turn.capturing).toBe(true);
    expect(h.formats).toEqual([{ sampleRate: 16_000, channels: 1 }]);
    expect(h.calls).toEqual(["create", "start"]);
  });

  it("settles one transcript from every segment, in order", async () => {
    const h = harness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false, maxSeconds: 1 });
    await turn.open();
    h.emit(new Int16Array(1_500).fill(2)); // the cap hands the first second out
    expect(h.seen).toHaveLength(1); // ...and it is already with the client
    h.emit(new Int16Array(200).fill(3));
    expect(await turn.finish()).toBe("seg1 seg2");
    expect(h.seen.map((segment) => segment.samples.length)).toEqual([1_000, 700]);
    expect(turn.capturing).toBe(false);
    expect(turn.zeroed()).toBe(true);
    expect(h.calls).toEqual(["create", "start", "stop"]);
  });

  it("a turn that heard nothing settles null and asks the client nothing", async () => {
    const h = harness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    await turn.open();
    expect(await turn.finish()).toBeNull();
    expect(h.seen).toEqual([]);
  });

  it("a turn that was never opened finishes null", async () => {
    const h = harness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    expect(await turn.finish()).toBeNull();
    expect(h.calls).toEqual([]);
  });

  it("a client failure fails the finish, and the microphone is already closed", async () => {
    const h = harness({ transcribe: async () => Promise.reject(new Error("asr_unreachable")) });
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    await turn.open();
    h.emit(new Int16Array(100).fill(1));
    await expect(turn.finish()).rejects.toThrow("asr_unreachable");
    expect(turn.capturing).toBe(false);
    expect(h.calls).toEqual(["create", "start", "stop"]);
  });

  it("a cap segment whose upload fails does not surface before finish is awaited", async () => {
    let rejections = 0;
    const onRejection = () => {
      rejections += 1;
    };
    process.on("unhandledRejection", onRejection);
    try {
      const h = harness({ transcribe: async () => Promise.reject(new Error("asr_unreachable")) });
      const turn = createCaptureTurn({ ...h.deps, closed: () => false, maxSeconds: 1 });
      await turn.open();
      h.emit(new Int16Array(1_200).fill(1));
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(rejections).toBe(0);
      await expect(turn.finish()).rejects.toThrow("asr_unreachable");
    } finally {
      process.off("unhandledRejection", onRejection);
    }
  });

  it("discard closes the microphone, zeroes, and sends nothing", async () => {
    const h = harness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    await turn.open();
    h.emit(new Int16Array(400).fill(5));
    turn.discard();
    expect(turn.capturing).toBe(false);
    expect(turn.zeroed()).toBe(true);
    expect(h.seen).toEqual([]);
    expect(h.calls).toEqual(["create", "start", "stop"]);
    expect(await turn.finish()).toBeNull();
  });

  it("a closed dialogue opens nothing", async () => {
    const h = harness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => true });
    expect(await turn.open()).toBe(false);
    expect(h.calls).toEqual([]);
  });

  it("a dialogue that closes while the stream is being created never starts it", async () => {
    let closed = false;
    const h = harness();
    const turn = createCaptureTurn({
      createStream: async (format) => {
        closed = true; // the RED lands during the lazy native import
        return h.deps.createStream(format);
      },
      transcribe: h.deps.transcribe,
      closed: () => closed,
    });
    expect(await turn.open()).toBe(false);
    expect(turn.capturing).toBe(false);
    // never started, and the native object the import created is released
    expect(h.calls).toEqual(["create", "stop"]);
  });

  it("says whether anything was heard, before and after the turn ends", async () => {
    const h = harness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    expect(turn.heard).toBe(false);
    await turn.open();
    expect(turn.heard).toBe(false);
    h.emit(new Int16Array(10).fill(1));
    expect(turn.heard).toBe(true);
    await turn.finish();
    expect(turn.heard).toBe(true);
    const silent = createCaptureTurn({ ...h.deps, closed: () => false });
    await silent.open();
    silent.discard();
    expect(silent.heard).toBe(false);
  });

  it("reads the level of the chunk that just arrived", async () => {
    const h = harness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    await turn.open();
    expect(turn.levelDbfs()).toBeUndefined();
    h.emit(new Int16Array(100).fill(16_384));
    expect(turn.levelDbfs()).toBeCloseTo(-6.02, 1);
  });
});

describe("a discard or a finish that lands while the turn opens (INT-559 review of #964, B2)", () => {
  it("a discard while the stream is being created never starts it, and releases what was created", async () => {
    const h = gatedHarness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    const opening = turn.open();
    turn.discard(); // the app leaves the foreground during the lazy native import
    h.releaseCreate();
    expect(await opening).toBe(false);
    expect(turn.capturing).toBe(false);
    expect(h.listeners()).toBe(0);
    expect(h.calls).toEqual(["create", "stop"]);
    h.emitPastTheWindow();
    expect(h.sent).toEqual([]);
    expect(turn.zeroed()).toBe(true);
    expect(await turn.finish()).toBeNull();
    expect(h.sent).toEqual([]);
  });

  it("a discard while the stream starts leaves it stopped once the start settles, and open says false", async () => {
    const h = gatedHarness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    const opening = turn.open();
    h.releaseCreate();
    await flush();
    expect(h.calls).toEqual(["create", "start"]);
    turn.discard(); // the app leaves the foreground while the platform brings the input up
    expect(h.listeners()).toBe(0);
    h.releaseStart();
    expect(await opening).toBe(false);
    expect(turn.capturing).toBe(false);
    expect(h.listeners()).toBe(0);
    expect(h.calls).toEqual(["create", "start", "started", "stop"]);
    h.emitPastTheWindow();
    expect(h.sent).toEqual([]);
    expect(turn.zeroed()).toBe(true);
    expect(await turn.finish()).toBeNull();
    expect(h.sent).toEqual([]);
  });

  it("a finish while the turn opens ends it: nothing opens behind the hand-over", async () => {
    const h = gatedHarness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    const opening = turn.open();
    expect(await turn.finish()).toBeNull(); // "Bitirdim" before the microphone is up
    h.releaseCreate();
    expect(await opening).toBe(false);
    expect(turn.capturing).toBe(false);
    expect(h.listeners()).toBe(0);
    expect(h.calls).toEqual(["create", "stop"]);
    h.emitPastTheWindow();
    expect(h.sent).toEqual([]);
  });

  it("near miss: a discard after the open settled closes the microphone at once, as before", async () => {
    const h = gatedHarness();
    const turn = createCaptureTurn({ ...h.deps, closed: () => false });
    const opening = turn.open();
    h.releaseCreate();
    await flush();
    h.releaseStart();
    expect(await opening).toBe(true);
    expect(turn.capturing).toBe(true);
    expect(h.listeners()).toBe(1);
    turn.discard();
    expect(turn.capturing).toBe(false);
    expect(h.listeners()).toBe(0);
    expect(h.calls).toEqual(["create", "start", "started", "stop"]);
    h.emitPastTheWindow();
    expect(h.sent).toEqual([]);
    expect(turn.zeroed()).toBe(true);
    expect(await turn.finish()).toBeNull();
  });
});
