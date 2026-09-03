/**
 * Dev-lane FreyaTTS client + session clip cache, pure parts (INT-233).
 * The daemon (port 8803, same box and prober as whisper/extract) takes
 * POST /synthesize {"text": ...} and answers WAV bytes.
 *
 * Invariant 22 mirror: no numeral may cross into any TTS. FreyaTTS rejects
 * digit-bearing text on its side; `assertSpeakableTr` throws BEFORE the
 * request ever leaves the app, so the guard holds even if the daemon's
 * check were ever relaxed. Agent speech is composed from catalog tr strings
 * (speech.ts), which are numeral-free by INT-198's pinned test.
 *
 * Cache contract: one synthesis per clip per session, name-keyed; clear()
 * drops the whole directory. These are AGENT-voice clips (synthesized from
 * catalog strings) — invariant 3 governs PATIENT audio, which keeps the
 * delete-after-upload posture in lib/voice.ts untouched. The expo-bound
 * filesystem and host probing live in clips.ts; everything here is pure and
 * node-testable.
 *
 * INT-237: a clip is synthesized one SENTENCE per request and assembled
 * here, because the daemon gives every clause boundary the same fixed gap
 * and cannot express a sentence break. `synthesizeClip` is the entry point
 * the clip store uses; `synthesizeWav` remains the single-request
 * primitive. See speechShaping.ts for the shaping contract and
 * docs/evidence/INT-237.md for the measurements.
 */
import { assembleClip, shapeForDelivery } from "./speechShaping";

export const TTS_PORT = 8803;

/**
 * The turn-latency budget, as files/03 §4.4 states it for `residency_tr` —
 * the only production voice profile:
 *
 *   "expected round-trip p50 (end of speech → first agent audio) …
 *    p95 ≈ 1684–2364 ms; may BEAT the displaced cloud stack"
 *
 * and §4.5 fixes what round-trip means: "last patient speech sample (VAD
 * end) → first agent audio sample played on the device."
 *
 * On the dev clip path that round-trip IS the synthesis. There is no SFU, no
 * RAN, no jitter buffer — the app POSTs to a daemon over loopback or the LAN
 * and plays the bytes the moment they land — so the time a lane takes to
 * answer is the whole of the wait the patient sits through, and the stated
 * round-trip is the honest ceiling to hold it to. A lane that cannot answer
 * inside the BEST of the stated band is not a slow lane, it is a lane that
 * cannot carry a turn.
 *
 * Why not §4.5's TTS-stage row instead. That row reads "TTS first byte | 0 ms
 * scripted / 140 ms dynamic (§4.9.1 row 11, measured; 520 ms on the row-12
 * fallback, and that is a hard architectural floor)" — and 520 ms is a TTFT
 * figure for the STREAMING production path. These daemons do not stream: one
 * POST returns the whole WAV, so there is no first byte to measure, and row
 * 12's own note calls 0.52 s Freya's TTFT floor rather than its clip time.
 * Measured on the host, Freya takes 1.03 s to answer with a single word
 * (docs/evidence/INT-249.md), so gating on 520 ms would reject the very tier
 * the blueprint designates as the acceptable fallback and leave the app with
 * no voice at all. The stage figure is the wrong quantity for this seam; the
 * round-trip figure is the right one.
 */
export const TURN_ROUND_TRIP_BUDGET_MS = 1684;

/**
 * Hard cap on ONE synthesis request — the worst of the same stated band.
 *
 * The asymmetry is deliberate and both ends are the blueprint's. Admission
 * holds a candidate lane to the BEST of §4.4's p95 band on a minimal probe,
 * because a lane chosen for the session should have headroom; a request
 * already in flight on the chosen lane is allowed the WORST of that band
 * before it is declared wedged, because failing a lane that is merely having
 * a bad sentence would cost the patient a voice change for nothing.
 *
 * It replaces a 30 s default. Under that default a wedged VoxCPM2 held each
 * sentence for half a minute, sequentially per sentence, and then failed the
 * whole dialogue to the manual steps (docs/evidence/INT-249.md).
 */
export const SYNTHESIZE_TIMEOUT_MS = 2364;

/**
 * The longest a patient may be left looking at "Soru hazırlanıyor…" for one
 * clip (INT-261).
 *
 * Both caps above bound ONE request. Nothing bounded the WHOLE clip, and the
 * layers between them multiply: `selectTtsLane` walks every (tier, host)
 * pair in sequence, each costing a health timeout plus a full probe
 * synthesis; `synthesizeWithFallback` may invalidate and re-walk that ladder
 * once per candidate; and `synthesizeClipWith` runs all of it once per
 * SENTENCE. Reported from the simulator with all five dev lanes answering
 * /health in milliseconds: a spinner, pixel-identical a minute apart. Every
 * layer was behaving exactly as designed.
 *
 * So this is the patient's bound rather than a lane's: ONE lane admission
 * plus ONE synthesis per sentence — the ladder's own two committed figures,
 * multiplied by the work the clip actually contains. No new duration is
 * invented here, and a clip that exceeds it is not slow, it is thrashing.
 * Past it the turn continues without a voice (stream.ts `speech_unavailable`),
 * which is the same trade INT-249 already made one level down.
 */
export function clipDeadlineMs(text: string): number {
  // INT-291: count the requests DELIVERY will make, not the sentences the
  // text has — merging below the floor means fewer requests, and a budget
  // that overcounts them buys the patient a longer spinner for nothing.
  const sentences = Math.max(1, shapeForDelivery(text).length);
  return TURN_ROUND_TRIP_BUDGET_MS + sentences * SYNTHESIZE_TIMEOUT_MS;
}

/**
 * `work`, or `tts_deadline` — whichever comes first.
 *
 * The abandoned work is NOT cancelled, deliberately: it is a clip synthesis
 * the clip store is already deduplicating by name, so letting it finish
 * lands the file in the cache for a later turn. What it may not do is hold
 * the turn. A rejection passes through untouched so the deadline never
 * masks the real reason a lane said no.
 */
export async function withDeadline<T>(work: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      work,
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error("tts_deadline")), ms);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Throws unless the text is safe to hand to the TTS: non-empty and free of
 * every Unicode decimal digit (invariant 22 — numbers never cross a
 * representation boundary unguarded).
 */
export function assertSpeakableTr(text: string): void {
  if (text.trim().length === 0) {
    throw new Error("tts_empty_text");
  }
  if (/\p{Nd}/u.test(text)) {
    throw new Error("tts_numeral_blocked");
  }
}

const BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/** RFC 4648 base64 for RN, where neither Buffer nor btoa is guaranteed. */
export function bytesToBase64(bytes: Uint8Array): string {
  let out = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i];
    const b = i + 1 < bytes.length ? bytes[i + 1] : 0;
    const c = i + 2 < bytes.length ? bytes[i + 2] : 0;
    out += BASE64_ALPHABET[a >> 2];
    out += BASE64_ALPHABET[((a & 0x03) << 4) | (b >> 4)];
    out += i + 1 < bytes.length ? BASE64_ALPHABET[((b & 0x0f) << 2) | (c >> 6)] : "=";
    out += i + 2 < bytes.length ? BASE64_ALPHABET[c & 0x3f] : "=";
  }
  return out;
}

const SAFE_ID = /^[a-z0-9_]+$/;

/**
 * Deterministic session cache key for a clip. Question clips key on the
 * question id; confirm clips on the sorted option-id set. Free-text values
 * never name a file — text steps share the question's generic confirm clip.
 */
export function clipName(
  kind: "question" | "confirm",
  questionId: string,
  valueIds?: string[],
): string {
  const parts = [questionId, ...(valueIds ?? []).slice().sort()];
  for (const part of parts) {
    if (!SAFE_ID.test(part)) {
      throw new Error("clip_name_unsafe");
    }
  }
  return `${kind === "question" ? "q" : "c"}_${parts.join("_")}.wav`;
}

export interface SynthesizeOptions {
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  /**
   * Abandons a request the caller no longer needs (INT-294). Admission races
   * every lane at once, and the losers must stop the moment a winner is
   * known — a probe nobody is waiting for is a request the dev box is still
   * serving.
   */
  signal?: AbortSignal;
}

/** POST /synthesize on a known base; throws on guard, transport or empty body. */
export async function synthesizeWav(
  base: string,
  text: string,
  options: SynthesizeOptions = {},
): Promise<Uint8Array> {
  assertSpeakableTr(text); // invariant 22 mirror — throws before any network call
  const { fetchImpl = fetch, timeoutMs = SYNTHESIZE_TIMEOUT_MS } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetchImpl(`${base}/synthesize`, {
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
  }
}

/**
 * Synthesizes one clip: the text is shaped into sentences, each sentence is
 * synthesized on its own, and the pieces are trimmed, faded and joined with
 * the shaped inter-sentence gaps (INT-237).
 *
 * Invariant 10 holds because shaping is punctuation-neutral on words — the
 * chunks are exact substrings of the input in order — and invariant 22
 * holds because the whole text is guarded here and each chunk is guarded
 * again inside `synthesizeWav`.
 */
export async function synthesizeClip(
  base: string,
  text: string,
  options: SynthesizeOptions = {},
): Promise<Uint8Array> {
  return synthesizeClipWith((sentence) => synthesizeWav(base, sentence, options), text);
}

/**
 * The same shaping and assembly, over an injected per-sentence synthesizer
 * rather than a fixed base (INT-249).
 *
 * A base is a decision taken once; a synthesizer is a decision taken per
 * request, which is what makes lane fallback possible at all — the clip
 * store hands in `synthesizeWithFallback` and each sentence independently
 * lands on whichever tier can actually speak it. Sentence chunking, gaps,
 * trimming and fades are INT-237's and are untouched.
 */
export async function synthesizeClipWith(
  synthesizeSentence: (sentence: string) => Promise<Uint8Array>,
  text: string,
): Promise<Uint8Array> {
  assertSpeakableTr(text);
  // INT-291: shapeForDelivery, not shapeForSpeech. The extra stage merges any
  // sentence below the lane's measured floor back into its neighbour — the
  // RED imperatives are the shortest strings in the product and the lane
  // invents a word in each when they are sent alone — and puts the turn-yield
  // tail on the last chunk. The single-chunk case is no longer special: it
  // carries that tail like any other last chunk.
  const chunks = shapeForDelivery(text);
  if (chunks.length === 0) {
    throw new Error("tts_empty_text");
  }
  // sequential, not parallel: the daemon synthesizes under a single lock,
  // so concurrent requests would queue anyway and only cost us timeouts.
  const parts: Uint8Array[] = [];
  for (const chunk of chunks) {
    parts.push(await synthesizeSentence(chunk.spoken));
  }
  return assembleClip(
    parts,
    chunks.map((chunk) => chunk.gapMs),
  );
}

/** The slice of a filesystem the clip store needs — expo-bound in clips.ts. */
export interface ClipFs {
  exists(path: string): Promise<boolean>;
  mkdirp(dir: string): Promise<void>;
  writeBase64(path: string, base64: string): Promise<void>;
  removeDir(dir: string): Promise<void>;
}

export interface ClipStore {
  /** Path to the cached clip, synthesizing at most once per session. */
  ensure(name: string, text: string): Promise<string>;
  /** Deletes the whole clip directory (unmount AND session end). */
  clear(): Promise<void>;
}

export function createClipStore(
  dir: string,
  fs: ClipFs,
  synth: (text: string) => Promise<Uint8Array>,
): ClipStore {
  const root = dir.endsWith("/") ? dir : `${dir}/`;
  // Concurrent ensures of one clip share a single synthesis: the session
  // pre-warm (INT-235) races the speaking driver for the same names, and
  // both must ride one request. A failed task is dropped so a later
  // ensure can retry honestly.
  const running = new Map<string, Promise<string>>();
  return {
    async ensure(name, text) {
      assertSpeakableTr(text); // defense in depth: no digit reaches synth
      const inFlight = running.get(name);
      if (inFlight !== undefined) {
        return inFlight;
      }
      const task = (async () => {
        const path = `${root}${name}`;
        if (await fs.exists(path)) {
          return path;
        }
        const bytes = await synth(text);
        await fs.mkdirp(root);
        await fs.writeBase64(path, bytesToBase64(bytes));
        return path;
      })();
      running.set(name, task);
      try {
        return await task;
      } finally {
        running.delete(name);
      }
    },
    async clear() {
      await fs.removeDir(root);
    },
  };
}
