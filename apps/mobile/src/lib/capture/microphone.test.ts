/**
 * INT-559 (review of #964, B2) — the one microphone a screen holds. The
 * dialogue and the voice-note pill prepare the platform's audio session
 * before a capture turn exists, so a discard has to reach an open wherever
 * it is suspended: in the prepare (expo-audio's setAudioModeAsync), in the
 * native stream's creation, or in its start. Each await is a gate here, and
 * every test drives a real capture turn over a fake stream in node.
 *
 * Every interleaving asserts the same four things: nothing capturing,
 * nothing listening, the stream stopped and released if one was created, and
 * no segment sent after the discard.
 */
import { describe, expect, it } from "vitest";

import { createMicrophone, type Microphone } from "./microphone";
import { createCaptureTurn } from "./turn";
import type { PcmChunk, PcmSegment, PcmStreamPort } from "./types";

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

interface Rig {
  microphone: Microphone;
  calls: string[];
  sent: PcmSegment[];
  listeners(): number;
  /** The owner closes for good: useDialogueSession's `closedRef.current = true`. */
  close(): void;
  emit(samples: Int16Array): void;
  releasePrepare(error?: Error): void;
  releaseCreate(): void;
  releaseStart(): void;
}

function rig(): Rig {
  const calls: string[] = [];
  const sent: PcmSegment[] = [];
  const listeners = new Set<(chunk: PcmChunk) => void>();
  const prepares: ((error?: Error) => void)[] = [];
  const creates: (() => void)[] = [];
  const starts: (() => void)[] = [];
  let closed = false;
  const port = (): PcmStreamPort => ({
    start: () => {
      calls.push("start");
      return new Promise<void>((resolve) => {
        starts.push(() => {
          calls.push("started");
          resolve();
        });
      });
    },
    stop: () => {
      calls.push("stop");
    },
    onBuffer: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  });
  const microphone = createMicrophone({
    prepare: () => {
      calls.push("prepare");
      return new Promise<void>((resolve, reject) => {
        prepares.push((error) => (error === undefined ? resolve() : reject(error)));
      });
    },
    createTurn: (turnClosed) =>
      createCaptureTurn({
        createStream: () => {
          calls.push("create");
          return new Promise<PcmStreamPort>((resolve) => {
            creates.push(() => resolve(port()));
          });
        },
        transcribe: async (segment) => {
          sent.push(segment);
          return "söz";
        },
        closed: turnClosed,
        maxSeconds: 1,
      }),
    closed: () => closed,
  });
  return {
    microphone,
    calls,
    sent,
    listeners: () => listeners.size,
    close: () => {
      closed = true;
    },
    emit(samples) {
      const data = samples.buffer.slice(
        samples.byteOffset,
        samples.byteOffset + samples.byteLength,
      ) as ArrayBuffer;
      for (const listener of listeners) {
        listener({ data, sampleRate: 1_000, channels: 1 });
      }
    },
    releasePrepare: (error) => prepares.shift()?.(error),
    releaseCreate: () => creates.shift()?.(),
    releaseStart: () => starts.shift()?.(),
  };
}

/** Walk one open through all three awaits. */
async function openFully(r: Rig): Promise<boolean> {
  const opening = r.microphone.open();
  r.releasePrepare();
  await flush();
  r.releaseCreate();
  await flush();
  r.releaseStart();
  return opening;
}

/** Nothing capturing, nothing held, nothing listening, and nothing sent — even past the window. */
function expectNothingLeft(r: Rig): void {
  expect(r.microphone.capturing).toBe(false);
  expect(r.microphone.current()).toBeNull();
  expect(r.listeners()).toBe(0);
  r.emit(new Int16Array(1_500).fill(7)); // a live one-second window would hand a segment out
  expect(r.sent).toEqual([]);
}

describe("createMicrophone", () => {
  it("opens one turn, and a caller arriving while it opens shares that open", async () => {
    const r = rig();
    const first = r.microphone.open();
    const second = r.microphone.open();
    r.releasePrepare();
    await flush();
    r.releaseCreate();
    await flush();
    r.releaseStart();
    expect(await Promise.all([first, second])).toEqual([true, true]);
    expect(r.microphone.capturing).toBe(true);
    expect(r.microphone.current()?.capturing).toBe(true);
    expect(r.calls).toEqual(["prepare", "create", "start", "started"]);
    expect(r.listeners()).toBe(1);
  });

  it("opens nothing while one is capturing, and nothing once the owner has closed", async () => {
    const r = rig();
    expect(await openFully(r)).toBe(true);
    expect(await r.microphone.open()).toBe(true);
    expect(r.calls).toEqual(["prepare", "create", "start", "started"]);
    const closed = rig();
    closed.close();
    expect(await closed.microphone.open()).toBe(false);
    expect(closed.calls).toEqual([]);
  });

  it("a platform failure of an open nobody abandoned rejects, and nothing is held", async () => {
    const r = rig();
    const opening = r.microphone.open();
    r.releasePrepare(new Error("session_busy"));
    await expect(opening).rejects.toThrow("session_busy");
    expect(r.microphone.current()).toBeNull();
    expect(r.calls).toEqual(["prepare"]);
  });

  it("take hands the capturing turn over unclosed, and its finish settles the words", async () => {
    const r = rig();
    await openFully(r);
    r.emit(new Int16Array(200).fill(2));
    const turn = r.microphone.take();
    expect(r.microphone.current()).toBeNull();
    expect(turn?.capturing).toBe(true);
    expect(await turn?.finish()).toBe("söz");
    expect(r.calls).toEqual(["prepare", "create", "start", "started", "stop"]);
    expect(r.listeners()).toBe(0);
  });
});

describe("a discard reaches the open wherever it is suspended (INT-559 review of #964, B2)", () => {
  it("during the audio-session prepare (setAudioModeAsync): no stream is ever created", async () => {
    const r = rig();
    const opening = r.microphone.open();
    r.microphone.discard(); // the app leaves the foreground while the session switches
    r.releasePrepare();
    expect(await opening).toBe(false);
    await flush();
    expect(r.calls).toEqual(["prepare"]);
    expectNothingLeft(r);
  });

  it("during the stream's creation: it is never started, and it is released", async () => {
    const r = rig();
    const opening = r.microphone.open();
    r.releasePrepare();
    await flush();
    expect(r.calls).toEqual(["prepare", "create"]);
    r.microphone.discard();
    r.releaseCreate();
    expect(await opening).toBe(false);
    expect(r.calls).toEqual(["prepare", "create", "stop"]);
    expectNothingLeft(r);
  });

  it("during the stream's start: it is stopped once the start settles", async () => {
    const r = rig();
    const opening = r.microphone.open();
    r.releasePrepare();
    await flush();
    r.releaseCreate();
    await flush();
    expect(r.calls).toEqual(["prepare", "create", "start"]);
    r.microphone.discard();
    expect(r.listeners()).toBe(0);
    r.releaseStart();
    expect(await opening).toBe(false);
    expect(r.calls).toEqual(["prepare", "create", "start", "started", "stop"]);
    expectNothingLeft(r);
  });

  it("a take while the open is in flight leaves nothing opening behind the hand-over", async () => {
    const r = rig();
    const opening = r.microphone.open();
    expect(r.microphone.take()).toBeNull(); // "Bitirdim" before the session switched
    r.releasePrepare();
    expect(await opening).toBe(false);
    await flush();
    expect(r.calls).toEqual(["prepare"]);
    expectNothingLeft(r);
  });

  it("the next open after a discard starts fresh rather than joining the abandoned one", async () => {
    const r = rig();
    const abandoned = r.microphone.open();
    r.microphone.discard(); // the app leaves the foreground...
    const reopened = r.microphone.open(); // ...and comes back mid-listen
    r.releasePrepare(); // the abandoned open's prepare
    r.releasePrepare(); // the fresh one's
    await flush();
    r.releaseCreate();
    await flush();
    r.releaseStart();
    expect(await Promise.all([abandoned, reopened])).toEqual([false, true]);
    expect(r.microphone.capturing).toBe(true);
    expect(r.calls.filter((call) => call === "create")).toHaveLength(1);
    expect(r.listeners()).toBe(1);
  });

  it("an abandoned open that then fails at the platform settles quietly", async () => {
    const r = rig();
    const opening = r.microphone.open();
    r.microphone.discard();
    r.releasePrepare(new Error("session_busy"));
    await expect(opening).resolves.toBe(false);
    expectNothingLeft(r);
  });

  it("near miss: a discard after the open settled closes the microphone at once, as before", async () => {
    const r = rig();
    expect(await openFully(r)).toBe(true);
    r.emit(new Int16Array(400).fill(3));
    r.microphone.discard();
    expect(r.calls).toEqual(["prepare", "create", "start", "started", "stop"]);
    expect(r.sent).toEqual([]);
    expectNothingLeft(r);
  });
});

describe("the dialogue unmounts while an open is pending (closedRef first, then the discard)", () => {
  const released: Record<"prepare" | "create" | "start", string[]> = {
    prepare: ["prepare"],
    create: ["prepare", "create", "stop"],
    start: ["prepare", "create", "start", "started", "stop"],
  };
  for (const phase of ["prepare", "create", "start"] as const) {
    it(`an unmount during ${phase} leaves nothing, and no later open opens`, async () => {
      const r = rig();
      const opening = r.microphone.open();
      if (phase !== "prepare") {
        r.releasePrepare();
        await flush();
      }
      if (phase === "start") {
        r.releaseCreate();
        await flush();
      }
      // useDialogueSession's unmount cleanup, in its order
      r.close();
      r.microphone.discard();
      r.releasePrepare();
      r.releaseCreate();
      r.releaseStart();
      expect(await opening).toBe(false);
      await flush();
      expect(r.calls).toEqual(released[phase]);
      expectNothingLeft(r);
      // a driver resumed past an await asks again after the unmount
      expect(await r.microphone.open()).toBe(false);
      expect(r.calls.filter((call) => call === "prepare")).toHaveLength(1);
      expectNothingLeft(r);
    });
  }

  it("a discard alone leaves the owner open: a later open opens, which is why the unmount closes first", async () => {
    const r = rig();
    const opening = r.microphone.open();
    r.microphone.discard();
    r.releasePrepare();
    expect(await opening).toBe(false);
    expect(await openFully(r)).toBe(true);
    expect(r.microphone.capturing).toBe(true);
    expect(r.calls.filter((call) => call === "prepare")).toHaveLength(2);
  });
});
