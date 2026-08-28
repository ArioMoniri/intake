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
 */

export const TTS_PORT = 8803;

/** Default cap for one clip synthesis; the daemon answers in seconds. */
const SYNTHESIZE_TIMEOUT_MS = 30_000;

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
  return {
    async ensure(name, text) {
      assertSpeakableTr(text); // defense in depth: no digit reaches synth
      const path = `${root}${name}`;
      if (await fs.exists(path)) {
        return path;
      }
      const bytes = await synth(text);
      await fs.mkdirp(root);
      await fs.writeBase64(path, bytesToBase64(bytes));
      return path;
    },
    async clear() {
      await fs.removeDir(root);
    },
  };
}
