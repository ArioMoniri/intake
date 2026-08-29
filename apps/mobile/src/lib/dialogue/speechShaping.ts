/**
 * Speech shaping for the dev-lane clip path (INT-237).
 *
 * The owner's report was that the spoken dialogue sounds awkward. Measured
 * on the FreyaTTS lane (docs/evidence/INT-237.md, 29 Aug 2026), three of the
 * causes sit on our side of the boundary and are fixed here:
 *
 *   1. The daemon's clause splitter gives EVERY boundary the same fixed
 *      120 ms gap, so a full stop is delivered exactly like a comma. On
 *      `Nasıl başladı? Seçenekler: …` the boundary after the question mark
 *      measured 90 ms — indistinguishable from a comma. Splitting at
 *      SENTENCE boundaries on our side and inserting the gap ourselves is
 *      the only way to express a sentence break; clause gaps stay the
 *      daemon's job, which is where 120 ms is about right.
 *   2. Leading silence measured 30–150 ms and trailing 0–250 ms, so turns
 *      began and ended raggedly. Trimming to a fixed head/tail makes every
 *      turn start and stop the same way.
 *   3. Two clips ended with zero trailing silence — a hard cut straight
 *      from speech to nothing, which clicks. A short raised-cosine fade on
 *      each edge removes that without audibly shortening the speech.
 *
 * INVARIANT 10 — scripted text is spoken verbatim. Shaping is
 * punctuation-neutral on words: every chunk's `text` is an exact substring
 * of the whitespace-collapsed input, the chunks appear in order, and they
 * cover the input completely. The only thing shaping may add is a terminal
 * mark on the SPOKEN form of a chunk that lacks one, which is what drives
 * interrogative prosody. `shapeForSpeech` is pinned on both properties in
 * speechShaping.test.ts.
 *
 * INVARIANT 22 — no numeral crosses into any TTS. Shaping neither creates
 * nor removes digits; the caller's `assertSpeakableTr` guard is unchanged
 * and still runs before any request leaves the app.
 *
 * What shaping does NOT do: it does not control the speaking RATE. The
 * daemon's duration head regresses log-frame-count from a MEAN-POOLED text
 * embedding, so its allocation tracks average character identity rather
 * than length — two single-chunk strings of 31 and 33 characters measured
 * 3.32 and 1.73 frames per character, a 1.9× rate difference. Nothing at
 * this seam can correct that; see the verdict in docs/evidence/INT-237.md.
 */

/** Marks that end a sentence. `…` is included: the catalog uses it. */
const TERMINALS = ".?!…";

/** Silence floor for trimming, in dBFS. Measured well under this voice's
 * speech floor and well over its noise floor. */
export const SILENCE_FLOOR_DBFS = -45;

/** Analysis grain for the silence scan. */
export const ANALYSIS_FRAME_MS = 10;

/** Silence kept before the first and after the last speech sample. */
export const KEEP_HEAD_MS = 15;
export const KEEP_TAIL_MS = 15;

/** Raised-cosine fade on each trimmed edge, so a cut cannot click. */
export const FADE_MS = 8;

/** Gap inserted between sentences — the break the daemon cannot express. */
export const SENTENCE_GAP_MS = 280;

export interface SpeechChunk {
  /** Exact substring of the whitespace-collapsed input. */
  text: string;
  /** What is sent to the TTS: `text`, plus a terminal mark if it had none. */
  spoken: string;
  /** Silence to insert AFTER this chunk; 0 on the last one. */
  gapMs: number;
}

/** Collapses every whitespace run to one space and trims the ends. */
export function collapseWhitespace(text: string): string {
  return text.replace(/\s+/gu, " ").trim();
}

/**
 * Splits into sentence chunks. Splits ONLY after a terminal mark followed
 * by whitespace — never at `,` `;` `:`, which are clause boundaries the
 * daemon already paces. Words are never altered.
 */
export function shapeForSpeech(text: string): SpeechChunk[] {
  const collapsed = collapseWhitespace(text);
  if (collapsed.length === 0) {
    return [];
  }

  const parts: string[] = [];
  let start = 0;
  let i = 0;
  while (i < collapsed.length) {
    if (!TERMINALS.includes(collapsed[i])) {
      i += 1;
      continue;
    }
    // absorb a run of marks ("?!", "...") into one boundary
    let end = i;
    while (end + 1 < collapsed.length && TERMINALS.includes(collapsed[end + 1])) {
      end += 1;
    }
    if (end + 1 >= collapsed.length) {
      break; // trailing mark: the tail is emitted below
    }
    if (collapsed[end + 1] === " ") {
      parts.push(collapsed.slice(start, end + 1));
      start = end + 2;
      i = start;
      continue;
    }
    // a mark glued to the next character (a decimal-less "v1.2"-shape, an
    // ellipsis mid-word) is not a sentence boundary
    i = end + 1;
  }
  if (start < collapsed.length) {
    parts.push(collapsed.slice(start));
  }

  const chunks = parts.filter((p) => p.length > 0);
  return chunks.map((text, index) => ({
    text,
    spoken: TERMINALS.includes(text[text.length - 1]) ? text : `${text}.`,
    gapMs: index === chunks.length - 1 ? 0 : SENTENCE_GAP_MS,
  }));
}

// ---------------------------------------------------------------------------
// WAV assembly. The daemon answers 16-bit mono PCM; these helpers trim, fade
// and join the per-sentence clips into the single file the clip cache stores.
// ---------------------------------------------------------------------------

export interface PcmClip {
  sampleRate: number;
  /** Interleaved 16-bit samples; mono, so one channel. */
  samples: Int16Array;
}

function fourcc(view: DataView, offset: number): string {
  return String.fromCharCode(
    view.getUint8(offset),
    view.getUint8(offset + 1),
    view.getUint8(offset + 2),
    view.getUint8(offset + 3),
  );
}

/**
 * Parses a 16-bit mono PCM WAV. Anything else throws rather than being
 * silently mangled — a clip we cannot read is a defect, not a turn.
 */
export function parseWav(bytes: Uint8Array): PcmClip {
  if (bytes.byteLength < 44) {
    throw new Error("wav_too_short");
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (fourcc(view, 0) !== "RIFF" || fourcc(view, 8) !== "WAVE") {
    throw new Error("wav_not_riff");
  }

  let sampleRate = 0;
  let channels = 0;
  let bits = 0;
  let dataOffset = -1;
  let dataLength = 0;

  let cursor = 12;
  while (cursor + 8 <= bytes.byteLength) {
    const id = fourcc(view, cursor);
    const size = view.getUint32(cursor + 4, true);
    const body = cursor + 8;
    if (id === "fmt ") {
      if (view.getUint16(body, true) !== 1) {
        throw new Error("wav_not_pcm");
      }
      channels = view.getUint16(body + 2, true);
      sampleRate = view.getUint32(body + 4, true);
      bits = view.getUint16(body + 14, true);
    } else if (id === "data") {
      dataOffset = body;
      dataLength = Math.min(size, bytes.byteLength - body);
    }
    cursor = body + size + (size % 2); // chunks are word-aligned
  }

  if (dataOffset < 0 || sampleRate === 0) {
    throw new Error("wav_no_data");
  }
  if (channels !== 1) {
    throw new Error("wav_not_mono");
  }
  if (bits !== 16) {
    throw new Error("wav_not_16bit");
  }

  const count = Math.floor(dataLength / 2);
  const samples = new Int16Array(count);
  for (let i = 0; i < count; i += 1) {
    samples[i] = view.getInt16(dataOffset + i * 2, true);
  }
  return { sampleRate, samples };
}

/** Serialises 16-bit mono PCM back into a WAV container. */
export function encodeWav(clip: PcmClip): Uint8Array {
  const dataBytes = clip.samples.length * 2;
  const out = new Uint8Array(44 + dataBytes);
  const view = new DataView(out.buffer);
  const ascii = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i += 1) {
      view.setUint8(offset + i, s.charCodeAt(i));
    }
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, clip.sampleRate, true);
  view.setUint32(28, clip.sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, dataBytes, true);
  for (let i = 0; i < clip.samples.length; i += 1) {
    view.setInt16(44 + i * 2, clip.samples[i], true);
  }
  return out;
}

/** First and last sample index whose analysis frame is above the floor. */
function speechBounds(samples: Int16Array, sampleRate: number): [number, number] {
  const hop = Math.max(1, Math.round((sampleRate * ANALYSIS_FRAME_MS) / 1000));
  const frames = Math.floor(samples.length / hop);
  const floor = Math.pow(10, SILENCE_FLOOR_DBFS / 20) * 32768;
  let first = -1;
  let last = -1;
  for (let f = 0; f < frames; f += 1) {
    let sum = 0;
    for (let i = f * hop; i < (f + 1) * hop; i += 1) {
      sum += samples[i] * samples[i];
    }
    if (Math.sqrt(sum / hop) >= floor) {
      if (first < 0) {
        first = f * hop;
      }
      last = (f + 1) * hop;
    }
  }
  if (first < 0) {
    return [0, samples.length]; // all quiet: leave it alone
  }
  return [first, Math.min(last, samples.length)];
}

/**
 * Trims a clip to a fixed head/tail of silence and fades each edge. Pure:
 * returns a new buffer and never mutates the input.
 */
export function trimAndFade(clip: PcmClip): PcmClip {
  const { samples, sampleRate } = clip;
  const [rawStart, rawEnd] = speechBounds(samples, sampleRate);
  const head = Math.round((sampleRate * KEEP_HEAD_MS) / 1000);
  const tail = Math.round((sampleRate * KEEP_TAIL_MS) / 1000);
  const start = Math.max(0, rawStart - head);
  const end = Math.min(samples.length, rawEnd + tail);
  const out = samples.slice(start, end);

  const fade = Math.round((sampleRate * FADE_MS) / 1000);
  if (fade > 0 && out.length > fade * 2) {
    for (let i = 0; i < fade; i += 1) {
      const gain = 0.5 * (1 - Math.cos((Math.PI * i) / fade));
      out[i] = Math.round(out[i] * gain);
      out[out.length - 1 - i] = Math.round(out[out.length - 1 - i] * gain);
    }
  }
  return { sampleRate, samples: out };
}

/**
 * Joins per-sentence clips, inserting each chunk's gap after it. Every part
 * must share a sample rate — a mismatch means two different voices or two
 * different daemons and is a defect, not something to resample around.
 */
export function joinClips(parts: PcmClip[], gapsMs: number[]): PcmClip {
  if (parts.length === 0) {
    throw new Error("clip_join_empty");
  }
  const sampleRate = parts[0].sampleRate;
  for (const part of parts) {
    if (part.sampleRate !== sampleRate) {
      throw new Error("clip_join_rate_mismatch");
    }
  }

  const gapSamples = parts.map((_, i) =>
    i === parts.length - 1 ? 0 : Math.round((sampleRate * (gapsMs[i] ?? 0)) / 1000),
  );
  const total =
    parts.reduce((n, p) => n + p.samples.length, 0) + gapSamples.reduce((n, g) => n + g, 0);

  const out = new Int16Array(total);
  let cursor = 0;
  parts.forEach((part, i) => {
    out.set(part.samples, cursor);
    cursor += part.samples.length + gapSamples[i]; // the gap stays zeroed
  });
  return { sampleRate, samples: out };
}

/** Trim + fade each part, then join with the shaped gaps. */
export function assembleClip(parts: Uint8Array[], gapsMs: number[]): Uint8Array {
  const clips = parts.map((bytes) => trimAndFade(parseWav(bytes)));
  return encodeWav(joinClips(clips, gapsMs));
}
