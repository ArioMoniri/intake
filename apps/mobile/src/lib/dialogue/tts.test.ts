/**
 * INT-233 dev-lane TTS client + session clip cache, pure parts.
 *
 * Invariant 22 mirror: no numeral may reach /synthesize — the guard throws
 * BEFORE any network call, and the FreyaTTS daemon independently rejects
 * digits. Cache contract: one synthesis per clip per session (name-keyed),
 * clear() drops the whole directory (component calls it on unmount AND on
 * session end). These are AGENT-voice clips composed from catalog strings —
 * invariant 3 governs PATIENT audio, which keeps the delete-after-upload
 * posture in lib/voice.ts untouched.
 */
import { describe, expect, it, vi } from "vitest";

import {
  assertSpeakableTr,
  bytesToBase64,
  clipName,
  createClipStore,
  synthesizeWav,
  TTS_PORT,
  type ClipFs,
} from "./tts";

describe("assertSpeakableTr (invariant 22 mirror)", () => {
  it("passes catalog Turkish", () => {
    expect(() => assertSpeakableTr("Şikâyetinizi kendi cümlelerinizle anlatın.")).not.toThrow();
    expect(() => assertSpeakableTr("Bir haftadan uzun süredir")).not.toThrow();
  });

  it("throws on any decimal digit, ASCII or otherwise", () => {
    expect(() => assertSpeakableTr("3 gündür")).toThrow();
    expect(() => assertSpeakableTr("günde ٣ kez")).toThrow(); // Arabic-Indic
    expect(() => assertSpeakableTr("0")).toThrow();
  });

  it("throws on empty speech — a silent clip is a defect, not a turn", () => {
    expect(() => assertSpeakableTr("")).toThrow();
    expect(() => assertSpeakableTr("   ")).toThrow();
  });
});

describe("bytesToBase64", () => {
  it("matches the RFC 4648 vectors", () => {
    expect(bytesToBase64(new Uint8Array([]))).toBe("");
    expect(bytesToBase64(new Uint8Array([0x4d]))).toBe("TQ==");
    expect(bytesToBase64(new Uint8Array([0x4d, 0x61]))).toBe("TWE=");
    expect(bytesToBase64(new Uint8Array([0x4d, 0x61, 0x6e]))).toBe("TWFu");
    // a WAV header start: "RIFF"
    expect(bytesToBase64(new Uint8Array([0x52, 0x49, 0x46, 0x46]))).toBe("UklGRg==");
  });
});

describe("clipName (deterministic session cache keys)", () => {
  it("question clips key on the question id", () => {
    expect(clipName("question", "complaint")).toBe("q_complaint.wav");
  });

  it("confirm clips key on the sorted value ids", () => {
    expect(clipName("confirm", "duration", ["days"])).toBe("c_duration_days.wav");
    expect(clipName("confirm", "complaint", ["pain", "fever"])).toBe(
      clipName("confirm", "complaint", ["fever", "pain"]),
    );
  });

  it("text steps get the generic confirm clip — free values never name a file", () => {
    expect(clipName("confirm", "extra")).toBe("c_extra.wav");
  });

  it("rejects anything that is not a plain id (path safety)", () => {
    expect(() => clipName("question", "../etc")).toThrow();
    expect(() => clipName("confirm", "duration", ["a/b"])).toThrow();
  });
});

function fakeFetch(status: number, body: Uint8Array) {
  return vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    arrayBuffer: async () => body.buffer.slice(0),
  })) as unknown as typeof fetch & ReturnType<typeof vi.fn>;
}

describe("synthesizeWav", () => {
  const wav = new Uint8Array([0x52, 0x49, 0x46, 0x46, 0x00]);

  it("POSTs the text to /synthesize and returns the bytes", async () => {
    const fetchImpl = fakeFetch(200, wav);
    const bytes = await synthesizeWav(`http://127.0.0.1:${TTS_PORT}`, "Sizi dinliyoruz.", {
      fetchImpl,
    });
    expect(Array.from(bytes)).toEqual(Array.from(wav));
    const [url, init] = (fetchImpl as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toBe(`http://127.0.0.1:${TTS_PORT}/synthesize`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ text: "Sizi dinliyoruz." });
  });

  it("throws BEFORE the network call when the text carries a digit", async () => {
    const fetchImpl = fakeFetch(200, wav);
    await expect(synthesizeWav("http://x", "3 gün", { fetchImpl })).rejects.toThrow();
    expect((fetchImpl as ReturnType<typeof vi.fn>).mock.calls.length).toBe(0);
  });

  it("throws on a non-2xx answer and on an empty body", async () => {
    await expect(
      synthesizeWav("http://x", "Merhaba", { fetchImpl: fakeFetch(503, wav) }),
    ).rejects.toThrow();
    await expect(
      synthesizeWav("http://x", "Merhaba", { fetchImpl: fakeFetch(200, new Uint8Array([])) }),
    ).rejects.toThrow();
  });
});

function memoryFs(): ClipFs & { files: Map<string, string>; removed: string[] } {
  const files = new Map<string, string>();
  const removed: string[] = [];
  return {
    files,
    removed,
    async exists(path: string) {
      return files.has(path);
    },
    async mkdirp() {},
    async writeBase64(path: string, base64: string) {
      files.set(path, base64);
    },
    async removeDir(dir: string) {
      removed.push(dir);
      for (const key of [...files.keys()]) {
        if (key.startsWith(dir)) {
          files.delete(key);
        }
      }
    },
  };
}

describe("createClipStore (one synthesis per clip per session)", () => {
  const wav = new Uint8Array([1, 2, 3]);

  it("synthesizes once, then serves the cached file", async () => {
    const fs = memoryFs();
    const synth = vi.fn(async () => wav);
    const store = createClipStore("cache/dialogue/", fs, synth);
    const first = await store.ensure("q_complaint.wav", "Bugün sizi buraya getiren nedir?");
    const second = await store.ensure("q_complaint.wav", "Bugün sizi buraya getiren nedir?");
    expect(first).toBe("cache/dialogue/q_complaint.wav");
    expect(second).toBe(first);
    expect(synth).toHaveBeenCalledTimes(1);
    expect(fs.files.get(first)).toBe(bytesToBase64(wav));
  });

  it("clear() removes the whole directory and a later ensure re-synthesizes", async () => {
    const fs = memoryFs();
    const synth = vi.fn(async () => wav);
    const store = createClipStore("cache/dialogue/", fs, synth);
    await store.ensure("q_duration.wav", "Bu şikâyetiniz ne zamandır var?");
    await store.clear();
    expect(fs.removed).toEqual(["cache/dialogue/"]);
    await store.ensure("q_duration.wav", "Bu şikâyetiniz ne zamandır var?");
    expect(synth).toHaveBeenCalledTimes(2);
  });

  it("refuses digit-bearing text before ever calling the synthesizer", async () => {
    const fs = memoryFs();
    const synth = vi.fn(async () => wav);
    const store = createClipStore("cache/dialogue/", fs, synth);
    await expect(store.ensure("q_bad.wav", "5 dakika bekleyin")).rejects.toThrow();
    expect(synth).not.toHaveBeenCalled();
    expect(fs.files.size).toBe(0);
  });
});
