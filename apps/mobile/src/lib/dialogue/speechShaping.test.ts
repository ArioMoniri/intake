/**
 * INT-237 speech shaping.
 *
 * The load-bearing test here is the invariant 10 pin: shaping is
 * punctuation-neutral on WORDS. The chunks must be exact substrings of the
 * whitespace-collapsed input, in order, covering it completely — so the
 * concatenated spoken text is still the scripted text, verbatim. It is
 * pinned twice: on hand-written cases, and over EVERY string in the
 * Turkish catalog, which is the actual material the agent speaks.
 */
import { describe, expect, it } from "vitest";

import { tr } from "../i18n/tr";
import {
  assembleClip,
  collapseWhitespace,
  encodeWav,
  FADE_MS,
  joinClips,
  KEEP_HEAD_MS,
  KEEP_TAIL_MS,
  parseWav,
  SENTENCE_GAP_MS,
  shapeForSpeech,
  trimAndFade,
  type PcmClip,
} from "./speechShaping";

const SR = 48_000;

function silence(ms: number): number[] {
  return new Array(Math.round((SR * ms) / 1000)).fill(0);
}

function tone(ms: number, amplitude = 12_000): number[] {
  const n = Math.round((SR * ms) / 1000);
  return Array.from({ length: n }, (_, i) =>
    Math.round(amplitude * Math.sin((2 * Math.PI * 220 * i) / SR)),
  );
}

function clipOf(samples: number[]): PcmClip {
  return { sampleRate: SR, samples: Int16Array.from(samples) };
}

describe("shapeForSpeech — invariant 10: words are never altered", () => {
  it("chunks concatenate back to the whitespace-collapsed original", () => {
    const text = "Nasıl başladı? Seçenekler: Aniden başladı veya Yavaş yavaş gelişti.";
    const chunks = shapeForSpeech(text);
    expect(chunks.map((c) => c.text).join(" ")).toBe(collapseWhitespace(text));
  });

  it("holds for every string in the Turkish catalog", () => {
    for (const [key, value] of Object.entries(tr)) {
      const collapsed = collapseWhitespace(value);
      if (collapsed.length === 0) {
        continue;
      }
      const chunks = shapeForSpeech(value);
      expect(chunks.length, key).toBeGreaterThan(0);
      // exact substrings, in order, covering the input completely
      expect(chunks.map((c) => c.text).join(" "), key).toBe(collapsed);
      for (const chunk of chunks) {
        expect(collapsed.includes(chunk.text), `${key}: ${chunk.text}`).toBe(true);
      }
    }
  });

  it("adds only a terminal mark to the spoken form, never a word", () => {
    for (const value of Object.values(tr)) {
      for (const chunk of shapeForSpeech(value)) {
        const added = chunk.spoken === chunk.text || chunk.spoken === `${chunk.text}.`;
        expect(added, chunk.text).toBe(true);
        // the words themselves survive untouched
        expect(chunk.spoken.replace(/\.$/u, "")).toBe(chunk.text.replace(/\.$/u, ""));
      }
    }
  });

  it("never introduces a digit (invariant 22 stays satisfiable)", () => {
    for (const value of Object.values(tr)) {
      const hadDigit = /\p{Nd}/u.test(value);
      for (const chunk of shapeForSpeech(value)) {
        if (!hadDigit) {
          expect(/\p{Nd}/u.test(chunk.spoken)).toBe(false);
        }
      }
    }
  });
});

describe("shapeForSpeech — where it splits", () => {
  it("splits at sentence marks and guarantees terminal punctuation", () => {
    const chunks = shapeForSpeech("Bir. İki? Üç! Dört");
    expect(chunks.map((c) => c.text)).toEqual(["Bir.", "İki?", "Üç!", "Dört"]);
    expect(chunks.map((c) => c.spoken)).toEqual(["Bir.", "İki?", "Üç!", "Dört."]);
  });

  it("never splits at a comma, semicolon or colon — those are the daemon's", () => {
    const text = "Seçenekler: Hafif, Orta veya Şiddetli; hepsi olabilir.";
    expect(shapeForSpeech(text)).toHaveLength(1);
  });

  it("gives every chunk but the last the sentence gap", () => {
    const chunks = shapeForSpeech("Bir cümle. İkinci cümle. Üçüncü cümle.");
    expect(chunks.map((c) => c.gapMs)).toEqual([SENTENCE_GAP_MS, SENTENCE_GAP_MS, 0]);
  });

  it("treats a run of marks as one boundary", () => {
    expect(shapeForSpeech("Gerçekten mi?! Evet.").map((c) => c.text)).toEqual([
      "Gerçekten mi?!",
      "Evet.",
    ]);
  });

  it("does not split on a mark glued to the next character", () => {
    expect(shapeForSpeech("Bir.iki üç.")).toHaveLength(1);
  });

  it("collapses awkward whitespace, including newlines and tabs", () => {
    const chunks = shapeForSpeech("  Bir   cümle.\n\tİkinci   cümle.  ");
    expect(chunks.map((c) => c.text)).toEqual(["Bir cümle.", "İkinci cümle."]);
  });

  it("returns nothing for empty or whitespace-only text", () => {
    expect(shapeForSpeech("")).toEqual([]);
    expect(shapeForSpeech("   \n ")).toEqual([]);
  });
});

describe("WAV round trip", () => {
  it("encode → parse preserves rate and samples", () => {
    const clip = clipOf([0, 1, -1, 32_767, -32_768, 1234]);
    const back = parseWav(encodeWav(clip));
    expect(back.sampleRate).toBe(SR);
    expect(Array.from(back.samples)).toEqual([0, 1, -1, 32_767, -32_768, 1234]);
  });

  it("rejects anything it cannot read rather than mangling it", () => {
    expect(() => parseWav(new Uint8Array(10))).toThrow("wav_too_short");
    const notRiff = encodeWav(clipOf(tone(20)));
    notRiff[0] = 0x00;
    expect(() => parseWav(notRiff)).toThrow("wav_not_riff");
  });

  it("reads a file carrying an extra chunk before data", () => {
    const base = encodeWav(clipOf(tone(20)));
    // splice a LIST chunk between fmt and data
    const extra = new Uint8Array(base.byteLength + 12);
    extra.set(base.subarray(0, 36), 0);
    const view = new DataView(extra.buffer);
    "LIST".split("").forEach((ch, i) => view.setUint8(36 + i, ch.charCodeAt(0)));
    view.setUint32(40, 4, true);
    view.setUint32(44, 0, true);
    extra.set(base.subarray(36), 48);
    view.setUint32(4, extra.byteLength - 8, true);
    expect(parseWav(extra).samples.length).toBe(parseWav(base).samples.length);
  });
});

describe("trimAndFade", () => {
  it("trims leading and trailing silence to the fixed head and tail", () => {
    const clip = clipOf([...silence(300), ...tone(500), ...silence(400)]);
    const out = trimAndFade(clip);
    const expected = Math.round((SR * (KEEP_HEAD_MS + 500 + KEEP_TAIL_MS)) / 1000);
    // the silence scan works on 10 ms frames, so allow one frame either way
    expect(Math.abs(out.samples.length - expected)).toBeLessThanOrEqual(Math.round(SR * 0.02));
  });

  it("fades both edges so a trimmed cut cannot click", () => {
    const out = trimAndFade(clipOf(tone(400)));
    const fade = Math.round((SR * FADE_MS) / 1000);
    expect(Math.abs(out.samples[0])).toBeLessThan(50);
    expect(Math.abs(out.samples[out.samples.length - 1])).toBeLessThan(50);
    // and full level is restored past the fade
    const mid = out.samples.slice(fade * 2, fade * 2 + 500);
    expect(Math.max(...Array.from(mid, Math.abs))).toBeGreaterThan(5_000);
  });

  it("leaves an all-quiet clip alone rather than deleting it", () => {
    const out = trimAndFade(clipOf(silence(100)));
    expect(out.samples.length).toBe(Math.round(SR * 0.1));
  });
});

describe("joinClips", () => {
  it("inserts exactly the requested gap between parts and none after the last", () => {
    const a = clipOf(tone(100));
    const b = clipOf(tone(100));
    const gap = 280;
    const out = joinClips([a, b], [gap, 0]);
    const gapSamples = Math.round((SR * gap) / 1000);
    expect(out.samples.length).toBe(a.samples.length + gapSamples + b.samples.length);
    // the gap really is silent
    const slice = out.samples.slice(a.samples.length, a.samples.length + gapSamples);
    expect(Math.max(...Array.from(slice, Math.abs))).toBe(0);
  });

  it("refuses a sample-rate mismatch instead of resampling", () => {
    const a = clipOf(tone(50));
    const b: PcmClip = { sampleRate: 24_000, samples: Int16Array.from(tone(50)) };
    expect(() => joinClips([a, b], [0, 0])).toThrow("clip_join_rate_mismatch");
  });

  it("refuses an empty join", () => {
    expect(() => joinClips([], [])).toThrow("clip_join_empty");
  });
});

describe("assembleClip", () => {
  it("trims each part and joins them with the shaped gaps", () => {
    const part = encodeWav(clipOf([...silence(200), ...tone(300), ...silence(200)]));
    const out = parseWav(assembleClip([part, part], [SENTENCE_GAP_MS, 0]));
    const perPart = Math.round((SR * (KEEP_HEAD_MS + 300 + KEEP_TAIL_MS)) / 1000);
    const gap = Math.round((SR * SENTENCE_GAP_MS) / 1000);
    expect(Math.abs(out.samples.length - (perPart * 2 + gap))).toBeLessThanOrEqual(
      Math.round(SR * 0.04),
    );
  });
});
