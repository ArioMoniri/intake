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

/**
 * Gap inserted between the agent's own sentences — the break the daemon
 * cannot express.
 *
 * INT-291 lowered this from INT-237's 280 ms. files/03 §4.2 mandates
 * `min_silence_duration >= 250 ms` for end-of-turn detection, so a pause
 * INSIDE the agent's turn that exceeds 250 ms is, by the runtime's own
 * definition, indistinguishable from the agent having finished. With barge-in
 * armed (bargeIn.ts) that is not a cosmetic point: it invites the patient into
 * the middle of a two-sentence question. 200 ms is under that floor and still
 * well above the daemon's fixed 120 ms clause gap, which is what INT-237
 * needed the number for in the first place.
 */
export const SENTENCE_GAP_MS = 200;

/**
 * Silence appended after the agent's LAST sentence, before the turn is the
 * patient's.
 *
 * This is the contour, and it is the whole of what "no emotions" is
 * addressable as at this seam. INT-237 trimmed every edge to a flat 15 ms, so
 * the agent stopped identically at a sentence boundary and at the end of its
 * own turn — the single most machine-like property of the delivery, because a
 * person does neither. Above the 250 ms end-of-turn floor for exactly the
 * reason SENTENCE_GAP_MS is below it: here, "the turn ended" is what the agent
 * means.
 *
 * It costs no interaction latency. The microphone is already open through the
 * whole clip (bargeIn.ts), so the patient can answer into this silence.
 */
export const TURN_YIELD_TAIL_MS = 300;

/**
 * The shortest text this seam will send as one TTS request, in non-space
 * characters.
 *
 * MEASURED, docs/evidence/INT-291.md, 2 Sep 2026, Freya lane
 * (`freyavoice/Freya-TTS` @ d124e07, normalizer disabled), synthesise ->
 * transcribe with the independent ASR daemon: every request under 13
 * non-space characters came back carrying a token nobody authored —
 * `"Tutun."` -> *"Tutun, atun."*, `"Arayın."` -> *"Arayın, arayın."*,
 * `"Bakmayın."` -> *"Bakmayın, ha!"*, `"Onaylayın."` -> *"Onaylayın, hı!"*,
 * 4 of 4. The shortest fragment that round-tripped clean was 13.
 *
 * That is not a prosody defect. A model that invents a word breaks CLAUDE.md
 * invariant 10 at the acoustic layer: the patient does not hear the string the
 * protocol authored. And the strings this bites are the shortest in the
 * product — the RED action imperatives, where invariant 21 says ambiguity is
 * the harm.
 *
 * INT-237 split at EVERY sentence boundary, which is how a safety script
 * became three sub-floor requests. `shapeForDelivery` keeps that split
 * wherever both sides clear the floor, and merges where they do not.
 */
export const MIN_CHUNK_CHARS = 13;

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

/** First and last sample index whose analysis frame is above the floor, or
 * null when the whole clip is under it. */
function speechBounds(samples: Int16Array, sampleRate: number): [number, number] | null {
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
    return null; // all quiet: leave it alone
  }
  return [first, Math.min(last, samples.length)];
}

/**
 * Trims a clip to a fixed head/tail of silence and fades each edge. Pure:
 * returns a new buffer and never mutates the input.
 */
export function trimAndFade(clip: PcmClip): PcmClip {
  const { samples, sampleRate } = clip;
  const bounds = speechBounds(samples, sampleRate);
  if (bounds === null) {
    return { sampleRate, samples: samples.slice() };
  }
  const [rawStart, rawEnd] = bounds;
  const head = Math.round((sampleRate * KEEP_HEAD_MS) / 1000);
  const tail = Math.round((sampleRate * KEEP_TAIL_MS) / 1000);
  const start = Math.max(0, rawStart - head);
  const end = Math.min(samples.length, rawEnd + tail);
  // INT-291: a clip that arrives with LESS lead than KEEP_HEAD_MS is PADDED,
  // not shaved. Measured (docs/evidence/INT-291.md) the VoxCPM2 lane returned
  // zero leading silence on 6 of 14 probes; trimming to a 15 ms head and then
  // fading 8 ms in put the fade on the first phoneme rather than on silence.
  // Padding puts the fade on silence this function inserted, so the fade can
  // never eat speech regardless of what the lane sent.
  const padHead = Math.max(0, head - (rawStart - start));
  const padTail = Math.max(0, tail - (end - rawEnd));
  const out = new Int16Array(padHead + (end - start) + padTail);
  out.set(samples.slice(start, end), padHead);

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

  // INT-291: the LAST gap is honoured too, because it is no longer a discard.
  // `shapeForDelivery` puts the turn-yield tail there, and a caller that means
  // "nothing after the last part" passes 0 — which is what INT-237's callers
  // already did.
  const gapSamples = parts.map((_, i) => Math.round((sampleRate * (gapsMs[i] ?? 0)) / 1000));
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

// ---------------------------------------------------------------------------
// The delivery stage (INT-291). `shapeForSpeech` answers "where are the
// sentence boundaries"; this answers "what may I actually send to a TTS, and
// how does the turn end". The two are separate because the floor below is a
// property of the LANE, measured on it, not a property of Turkish sentences —
// and `shapeForSpeech`'s invariant-10 pin over the whole catalog must keep
// testing the splitter on its own terms.
// ---------------------------------------------------------------------------

/** Non-space characters, which is what the lane's failure sorted on. */
function weight(text: string): number {
  return text.replace(/\s+/gu, "").length;
}

/**
 * Sentence chunks, merged up to `MIN_CHUNK_CHARS` and carrying the turn
 * contour. This is what the clip path sends.
 *
 * INVARIANT 10 is preserved through the merge, not weakened by it: chunks are
 * joined with the single space that already separated them in the
 * whitespace-collapsed input, so every `text` is still an exact substring of
 * that input, the chunks are still in order, and they still cover it
 * completely. Merging can only make a chunk longer; it can never make one that
 * is not in the source.
 */
export function shapeForDelivery(text: string): SpeechChunk[] {
  const sentences = shapeForSpeech(text);
  if (sentences.length === 0) {
    return [];
  }

  // Accumulate forward until the running chunk clears the floor.
  const merged: string[] = [];
  let pending = "";
  for (const sentence of sentences) {
    pending = pending === "" ? sentence.text : `${pending} ${sentence.text}`;
    if (weight(pending) >= MIN_CHUNK_CHARS) {
      merged.push(pending);
      pending = "";
    }
  }
  if (pending !== "") {
    // A short tail merges BACKWARDS. There is nothing after it to grow into,
    // and sending it alone is the defect the floor exists for. When it is the
    // only chunk there is nothing to merge with either — the honest limit:
    // this stage may not pad a short turn with words nobody authored.
    if (merged.length === 0) {
      merged.push(pending);
    } else {
      merged[merged.length - 1] = `${merged[merged.length - 1]} ${pending}`;
    }
  }

  return merged.map((chunkText, index) => ({
    text: chunkText,
    spoken: TERMINALS.includes(chunkText[chunkText.length - 1]) ? chunkText : `${chunkText}.`,
    gapMs: index === merged.length - 1 ? TURN_YIELD_TAIL_MS : SENTENCE_GAP_MS,
  }));
}
