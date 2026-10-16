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
  encodeWav,
  KEEP_HEAD_MS,
  KEEP_TAIL_MS,
  parseWav,
  SENTENCE_GAP_MS,
  TURN_YIELD_TAIL_MS,
} from "./speechShaping";
import {
  assertSpeakableTr,
  bytesToBase64,
  clipDeadlineMs,
  clipName,
  createClipStore,
  synthesizeClip,
  SYNTHESIZE_TIMEOUT_MS,
  TURN_ROUND_TRIP_BUDGET_MS,
  withDeadline,
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

describe("synthesizeClip (INT-237: one request per sentence, then assembled)", () => {
  const SR = 48_000;

  function wavOf(ms: number): Uint8Array {
    const n = Math.round((SR * ms) / 1000);
    const samples = Int16Array.from({ length: n }, (_, i) =>
      Math.round(9_000 * Math.sin((2 * Math.PI * 220 * i) / SR)),
    );
    return encodeWav({ sampleRate: SR, samples });
  }

  /** Answers every request with a fresh 200 ms clip, recording the texts. */
  function recordingFetch() {
    const texts: string[] = [];
    const impl = vi.fn(async (_url: string, init: RequestInit) => {
      texts.push(JSON.parse(init.body as string).text);
      const body = wavOf(200);
      return {
        ok: true,
        status: 200,
        arrayBuffer: async () =>
          body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength),
      };
    }) as unknown as typeof fetch & ReturnType<typeof vi.fn>;
    return { impl, texts };
  }

  it("sends one request per sentence, each verbatim plus its terminal mark", async () => {
    const { impl, texts } = recordingFetch();
    await synthesizeClip(
      "http://x",
      "Nasıl başladı? Seçenekler: Aniden başladı veya Yavaş yavaş gelişti.",
      { fetchImpl: impl },
    );
    expect(texts).toEqual([
      "Nasıl başladı?",
      "Seçenekler: Aniden başladı veya Yavaş yavaş gelişti.",
    ]);
  });

  it("the concatenated spoken text is the original, verbatim (invariant 10)", async () => {
    const original =
      "Sizi şöyle anladık: Ağrı ve Ateş. Doğruysa onaylayın; isterseniz düzeltmeyi söyleyin.";
    const { impl, texts } = recordingFetch();
    await synthesizeClip("http://x", original, { fetchImpl: impl });
    // both sentences already end in a mark, so the spoken forms are the
    // scripted text unchanged and rejoin to it exactly
    expect(texts.join(" ")).toBe(original);
  });

  it("joins the parts with a real inter-sentence gap", async () => {
    // INT-291: both halves must clear MIN_CHUNK_CHARS or delivery merges them
    // into one request, and there is no gap to find. "Bir cümle. İki cümle."
    // — the old fixture — is two nine-character sentences, which is exactly
    // the shape the measured floor now refuses to send.
    const { impl } = recordingFetch();
    const two = await synthesizeClip(
      "http://x",
      "Söyledikleriniz ekrana yazıldı. Kontrol edip onaylayın.",
      { fetchImpl: impl },
    );
    const one = await synthesizeClip("http://x", "Söyledikleriniz ekrana yazıldı.", {
      fetchImpl: impl,
    });
    const gap = Math.round((SR * SENTENCE_GAP_MS) / 1000);
    const yieldTail = Math.round((SR * TURN_YIELD_TAIL_MS) / 1000);
    // every turn now ends with the yield tail, so one part is the single
    // clip minus that tail
    const part = parseWav(one).samples.length - yieldTail;
    expect(parseWav(two).samples.length).toBe(part * 2 + gap + yieldTail);
  });

  it("still refuses a digit before any network call", async () => {
    const { impl } = recordingFetch();
    await expect(synthesizeClip("http://x", "3 gün önce.", { fetchImpl: impl })).rejects.toThrow(
      "tts_numeral_blocked",
    );
    expect((impl as ReturnType<typeof vi.fn>).mock.calls.length).toBe(0);
  });

  it("trims a single-sentence clip too, so every turn starts the same way", async () => {
    const lead = Math.round(SR * 0.3);
    const speech = Int16Array.from({ length: Math.round(SR * 0.2) }, (_, i) =>
      Math.round(9_000 * Math.sin((2 * Math.PI * 220 * i) / SR)),
    );
    const padded = new Int16Array(lead + speech.length);
    padded.set(speech, lead);
    const body = encodeWav({ sampleRate: SR, samples: padded });
    const impl = vi.fn(async () => ({
      ok: true,
      status: 200,
      arrayBuffer: async () =>
        body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength),
    })) as unknown as typeof fetch;

    const out = parseWav(await synthesizeClip("http://x", "Tek cümle.", { fetchImpl: impl }));
    // The 300 ms of ragged lead is gone and the shape is the contract's:
    // kept head + speech + kept tail + the turn-yield tail (INT-291). The
    // silence scan works on 10 ms frames, so allow one frame either way.
    const expected = Math.round(
      (SR * (KEEP_HEAD_MS + 200 + KEEP_TAIL_MS + TURN_YIELD_TAIL_MS)) / 1000,
    );
    expect(Math.abs(out.samples.length - expected)).toBeLessThanOrEqual(Math.round(SR * 0.02));
    // and the head really is silence, not a faded first phoneme
    const head = Math.round((SR * KEEP_HEAD_MS) / 1000);
    expect(Math.max(...Array.from(out.samples.slice(0, head), Math.abs))).toBe(0);
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

  it("concurrent ensures of one clip share a single synthesis (pre-warm race, INT-235)", async () => {
    const fs = memoryFs();
    let release: (() => void) | null = null;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const synth = vi.fn(async () => {
      await gate;
      return wav;
    });
    const store = createClipStore("cache/dialogue/", fs, synth);
    const race = Promise.all([
      store.ensure("q_onset.wav", "Nasıl başladı?"),
      store.ensure("q_onset.wav", "Nasıl başladı?"),
    ]);
    release!();
    const [first, second] = await race;
    expect(first).toBe(second);
    expect(synth).toHaveBeenCalledTimes(1);
  });

  it("refuses digit-bearing text before ever calling the synthesizer", async () => {
    const fs = memoryFs();
    const synth = vi.fn(async () => wav);
    const store = createClipStore("cache/dialogue/", fs, synth);
    await expect(store.ensure("q_bad.wav", "5 dakika bekleyin")).rejects.toThrow();
    expect(synth).not.toHaveBeenCalled();
    expect(fs.files.size).toBe(0);
  });

  it("hands the clip's name to the synthesizer, which finishes it for its place (INT-497)", async () => {
    // A lead-in and a question are finished differently (clipFinish.ts); the
    // name is how the store's caller tells them apart. It is a cache key the
    // app minted, never anything the patient said.
    const fs = memoryFs();
    const synth = vi.fn(async (_text: string, _context?: unknown, _name?: string) => wav);
    const store = createClipStore("cache/dialogue/", fs, synth);
    await store.ensure(
      "l_acknowledgement_dialogue_delivery_thanks_a.wav",
      "Teşekkürler.",
      "acknowledgement",
    );
    expect(synth.mock.calls[0][2]).toBe("l_acknowledgement_dialogue_delivery_thanks_a.wav");
  });
});

// INT-261 — the patient's turn has a deadline; the TTS ladder does not.
//
// Reported from the simulator with all five dev lanes healthy and reachable:
// "Soru hazırlanıyor…" and a spinner, pixel-identical a minute apart. Not
// unreachable — unbounded. `selectTtsLane` walks every (tier, host) pair in
// sequence, and each pair costs up to a health timeout plus a full probe
// synthesis; `synthesizeWithFallback` may then invalidate and re-walk that
// ladder once per candidate; and `synthesizeClipWith` runs that whole thing
// once per SENTENCE. Multiply it out and a clip can legitimately take
// minutes while every /health returns two hundred.
//
// Every one of those layers is defensible on its own, which is why the fix
// does not live in any of them: it lives where the patient is waiting. A
// clip gets one lane admission plus one synthesis per sentence — both
// numbers already committed and sourced (files/03 §4.4) — and past that the
// turn goes on without a voice. Nothing here invents a duration.
describe("clipDeadlineMs / withDeadline — a turn cannot wait forever (INT-261)", () => {
  it("allows one lane admission plus one synthesis per REQUEST", () => {
    const one = "Sizi bugün hekime getiren nedir?";
    expect(clipDeadlineMs(one)).toBe(TURN_ROUND_TRIP_BUDGET_MS + SYNTHESIZE_TIMEOUT_MS);
    const three =
      "Söyledikleriniz ekrana yazıldı. Kontrol edip onaylayın. Bir haftadan uzun süredir.";
    expect(clipDeadlineMs(three)).toBe(TURN_ROUND_TRIP_BUDGET_MS + 3 * SYNTHESIZE_TIMEOUT_MS);
  });

  it("counts the requests delivery will MAKE, not the sentences the text has", () => {
    // INT-291: "Şimdi nasıl?" is 11 non-space characters, under the measured
    // floor, so it is merged rather than sent — two requests, not three. A
    // budget that counted sentences would buy the patient a third of a minute
    // of spinner for a request nobody is going to make.
    const merged = "Ağrınız ne kadar sürdü? Nerede başladı? Şimdi nasıl?";
    expect(clipDeadlineMs(merged)).toBe(TURN_ROUND_TRIP_BUDGET_MS + 2 * SYNTHESIZE_TIMEOUT_MS);
  });

  it("never returns less than a single-sentence budget", () => {
    expect(clipDeadlineMs("Merhaba")).toBeGreaterThanOrEqual(
      TURN_ROUND_TRIP_BUDGET_MS + SYNTHESIZE_TIMEOUT_MS,
    );
  });

  it("passes a result that arrives in time straight through", async () => {
    await expect(withDeadline(Promise.resolve("clip.wav"), 50)).resolves.toBe("clip.wav");
  });

  it("passes a rejection through unchanged — the deadline never masks a real error", async () => {
    await expect(withDeadline(Promise.reject(new Error("tts_unavailable")), 50)).rejects.toThrow(
      "tts_unavailable",
    );
  });

  it("rejects with tts_deadline when the work never settles", async () => {
    // The hang exactly as reported: a promise that simply never resolves.
    await expect(withDeadline(new Promise<string>(() => {}), 10)).rejects.toThrow("tts_deadline");
  });

  it("does not keep the process alive waiting on a timer it no longer needs", async () => {
    vi.useFakeTimers();
    try {
      const cleared = vi.spyOn(globalThis, "clearTimeout");
      await withDeadline(Promise.resolve("done"), 60_000);
      expect(cleared).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });
});
