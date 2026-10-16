/**
 * INT-497 — every clip the dialogue stores is finished the same way, so two
 * clips of one turn join without a seam.
 *
 * A seam has three parts and each is pinned here:
 *   1. dead air: the pause between a lead-in and its question is exactly the
 *      pause between two sentences INSIDE one clip (KEEP_TAIL + SENTENCE_GAP +
 *      KEEP_HEAD), so a join cannot be heard as a join;
 *   2. the turn's own end: the question keeps the turn-yield tail, because
 *      there the pause MEANS "your turn" (INT-291);
 *   3. level: every clip is brought to one loudness (loudness.ts).
 * And the property that outranks all three: no word is ever cut (invariant 10).
 */
import { describe, expect, it } from "vitest";

import { clipRoleOf, finishClip, finishingSynth } from "./clipFinish";
import { deliveryClipName } from "./deliveryClips";
import { LOUDNESS_TARGET_LUFS, integratedLoudness } from "./loudness";
import {
  ANALYSIS_FRAME_MS,
  KEEP_HEAD_MS,
  KEEP_TAIL_MS,
  SENTENCE_GAP_MS,
  SILENCE_FLOOR_DBFS,
  TURN_YIELD_TAIL_MS,
  encodeWav,
  parseWav,
  type PcmClip,
} from "./speechShaping";
import { clipName } from "./tts";

const RATE = 24_000;

/** A "spoken" clip: `leadMs` of silence, a tone for `speechMs`, `trailMs` of silence. */
function spoken(leadMs: number, speechMs: number, trailMs: number, amplitude = 0.3): Uint8Array {
  const at = (ms: number) => Math.round((RATE * ms) / 1000);
  const samples = new Int16Array(at(leadMs) + at(speechMs) + at(trailMs));
  for (let i = 0; i < at(speechMs); i += 1) {
    samples[at(leadMs) + i] = Math.round(
      amplitude * 32767 * Math.sin((2 * Math.PI * 220 * i) / RATE),
    );
  }
  return encodeWav({ sampleRate: RATE, samples });
}

/** Leading and trailing silence, by the same frame analysis the trim uses. */
function edgesMs(clip: PcmClip): { lead: number; trail: number; voiced: number } {
  const hop = Math.round((RATE * ANALYSIS_FRAME_MS) / 1000);
  const floor = Math.pow(10, SILENCE_FLOOR_DBFS / 20) * 32768;
  const frames = Math.floor(clip.samples.length / hop);
  let first = -1;
  let last = -1;
  let voiced = 0;
  for (let f = 0; f < frames; f += 1) {
    let sum = 0;
    for (let i = f * hop; i < (f + 1) * hop; i += 1) {
      sum += clip.samples[i] * clip.samples[i];
    }
    if (Math.sqrt(sum / hop) >= floor) {
      voiced += 1;
      if (first < 0) {
        first = f;
      }
      last = f;
    }
  }
  return {
    lead: first * ANALYSIS_FRAME_MS,
    trail: (frames - 1 - last) * ANALYSIS_FRAME_MS,
    voiced,
  };
}

describe("clipRoleOf — which clips lead into a question and which end the turn", () => {
  it("a delivery line leads; a question or a read-back ends the turn", () => {
    expect(clipRoleOf(deliveryClipName("dialogue.delivery.thanks.a", "acknowledgement"))).toBe(
      "lead",
    );
    expect(clipRoleOf(clipName("question", "onset"))).toBe("turn_end");
    expect(clipRoleOf(clipName("confirm", "onset", ["today"]))).toBe("turn_end");
  });
});

describe("finishClip — a lead-in joins its question like a sentence boundary", () => {
  it("ends a lead with exactly the sentence pause, minus the next clip's head", () => {
    const lead = parseWav(finishClip(spoken(180, 700, 420), "lead"));
    const question = parseWav(finishClip(spoken(5, 900, 90), "turn_end"));
    const joined = edgesMs(lead).trail + edgesMs(question).lead;
    const insideOneClip = KEEP_TAIL_MS + SENTENCE_GAP_MS + KEEP_HEAD_MS;
    expect(Math.abs(joined - insideOneClip)).toBeLessThanOrEqual(2 * ANALYSIS_FRAME_MS);
  });

  it("keeps the turn-yield tail on the clip that ends the turn", () => {
    const question = parseWav(finishClip(spoken(5, 900, 0), "turn_end"));
    expect(
      Math.abs(edgesMs(question).trail - (KEEP_TAIL_MS + TURN_YIELD_TAIL_MS)),
    ).toBeLessThanOrEqual(2 * ANALYSIS_FRAME_MS);
  });

  it("brings the clip to the loudness target", () => {
    const quiet = parseWav(finishClip(spoken(50, 1200, 50, 0.05), "lead"));
    expect(integratedLoudness(quiet.samples, RATE)).toBeCloseTo(LOUDNESS_TARGET_LUFS, 0);
  });

  it("never cuts a voiced frame — the words are all there (invariant 10)", () => {
    const raw = parseWav(spoken(300, 1100, 500));
    const finished = parseWav(finishClip(encodeWav(raw), "lead"));
    expect(edgesMs(finished).voiced).toBeGreaterThanOrEqual(edgesMs(raw).voiced - 1);
  });

  it("is stable: finishing a finished clip changes neither its length nor its level", () => {
    const once = finishClip(spoken(120, 900, 200), "turn_end");
    const twice = finishClip(once, "turn_end");
    const a = parseWav(once);
    const b = parseWav(twice);
    expect(Math.abs(a.samples.length - b.samples.length)).toBeLessThanOrEqual(
      Math.round((RATE * ANALYSIS_FRAME_MS) / 1000),
    );
    expect(integratedLoudness(b.samples, RATE)!).toBeCloseTo(
      integratedLoudness(a.samples, RATE)!,
      1,
    );
  });

  it("leaves an all-silent clip silent rather than inventing a level for it", () => {
    const silent = parseWav(finishClip(spoken(400, 0, 0), "turn_end"));
    expect(silent.samples.every((sample) => sample === 0)).toBe(true);
  });
});

describe("finishingSynth — what the clip store's synthesizer becomes", () => {
  it("finishes each clip by the role its name gives it", async () => {
    const raw = spoken(200, 800, 400);
    const synth = finishingSynth(async () => raw);
    const lead = parseWav(
      await synth(
        "Teşekkürler.",
        "acknowledgement",
        deliveryClipName("dialogue.delivery.thanks.a", "acknowledgement"),
      ),
    );
    const question = parseWav(
      await synth("Nasıl başladı?", "routine", clipName("question", "onset")),
    );
    expect(edgesMs(question).trail - edgesMs(lead).trail).toBeGreaterThanOrEqual(
      TURN_YIELD_TAIL_MS - SENTENCE_GAP_MS - 2 * ANALYSIS_FRAME_MS,
    );
  });

  it("stores a body it cannot read exactly as it came — finishing never costs the voice", async () => {
    const opaque = new Uint8Array([1, 2, 3, 4]);
    const synth = finishingSynth(async () => opaque);
    expect(await synth("Teşekkürler.", "acknowledgement", "l_x.wav")).toBe(opaque);
  });
});
