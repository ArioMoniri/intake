/**
 * The last step of every clip the dialogue stores (INT-497): trim, one
 * loudness, and the tail its place in the turn calls for.
 *
 * Before this, the two clip sources were finished differently and joined
 * worse. The self-hosted lanes were shaped (INT-237/INT-291) and every clip,
 * lead-in or question, ended on the 300 ms turn-yield tail; the George clips
 * came back from the vendor untouched. A turn then played its lead-in and its
 * question as two players, one after the other, and the patient heard:
 *
 *   lead-in … [turn-yield tail] [player switch dead air] [vendor lead silence] … question
 *
 * — a pause longer than the 250 ms end-of-turn floor in the MIDDLE of the
 * agent's turn (which invites the patient to start answering a question not
 * yet asked), plus a step in level. Measured: docs/evidence/INT-497.md.
 *
 * After it, a lead-in ends on exactly the pause a sentence boundary has
 * inside one clip (SENTENCE_GAP_MS after KEEP_TAIL_MS, and the next clip
 * brings its KEEP_HEAD_MS), the turn's last clip keeps the turn-yield tail
 * where the pause MEANS "your turn", every clip is at one loudness, and the
 * player queues them with no switch between (useDialogueSession). A join is
 * then indistinguishable from a sentence boundary — which is what seamless
 * means for one speaker.
 *
 * Invariant 10: trimming cuts only below the silence floor and pads rather
 * than shaves (speechShaping.trimAndFade); loudness is a gain. No word moves.
 */
import { deliveryClipName } from "./deliveryClips";
import type { DeliveryContext } from "./deliveryContext";
import { normaliseLoudness } from "./loudness";
import {
  SENTENCE_GAP_MS,
  TURN_YIELD_TAIL_MS,
  encodeWav,
  joinClips,
  parseWav,
  trimAndFade,
} from "./speechShaping";

/** Where a clip sits in its turn: in front of the question, or at its end. */
export type ClipRole = "lead" | "turn_end";

/** The prefix every delivery-line clip carries (deliveryClips.deliveryClipName). */
const LEAD_PREFIX = deliveryClipName("x", "routine").slice(0, 2);

/**
 * A delivery line — welcome, lead-in, transition, acknowledgement — is only
 * ever said in front of a question. Questions and read-backs end the turn.
 */
export function clipRoleOf(clipName: string): ClipRole {
  return clipName.startsWith(LEAD_PREFIX) ? "lead" : "turn_end";
}

/** The silence a clip ends on, after its own KEEP_TAIL_MS. */
function tailFor(role: ClipRole): number {
  return role === "lead" ? SENTENCE_GAP_MS : TURN_YIELD_TAIL_MS;
}

/** Trim + fade, one loudness, then the role's tail. WAV in, WAV out. */
export function finishClip(wav: Uint8Array, role: ClipRole): Uint8Array {
  const shaped = normaliseLoudness(trimAndFade(parseWav(wav)));
  return encodeWav(joinClips([shaped], [tailFor(role)]));
}

type StoreSynth = (text: string, context?: DeliveryContext, name?: string) => Promise<Uint8Array>;

/**
 * The clip store's synthesizer, with every clip finished for its place in the
 * turn (clips.ts wraps both clip sources in this). Finishing is an
 * improvement, never a gate: a body it cannot read is stored as it came, so a
 * lane that answers a format this module does not parse still speaks.
 */
export function finishingSynth(synth: StoreSynth): StoreSynth {
  return async (text, context, name) => {
    const bytes = await synth(text, context, name);
    try {
      return finishClip(bytes, clipRoleOf(name ?? ""));
    } catch {
      return bytes;
    }
  };
}
