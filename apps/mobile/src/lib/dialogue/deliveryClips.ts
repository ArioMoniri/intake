/**
 * The voice seam of conversational delivery (INT-414): naming a delivery
 * line's clip, and settling one turn's clips so a lead-in can never make the
 * question late.
 *
 * Pure and node-testable. The clip store and the player live in
 * useDialogueSession; this module only decides WHICH clips play, which is the
 * part that has to be provable without a device.
 */
import type { DeliveryContext } from "./deliveryContext";
import { withDeadline } from "./tts";

/**
 * The session-cache file name for a delivery line's clip in one delivery
 * context. The same line in two contexts is two clips — the INT-415 profiles
 * differ — so the context is part of the name and a cache hit is never the
 * wrong voice. The `l_` prefix keeps them apart from `q_`/`c_` clips.
 */
export function deliveryClipName(key: string, context: DeliveryContext): string {
  return `l_${context}_${key.toLowerCase().replace(/[^a-z0-9]+/g, "_")}.wav`;
}

export interface SettleOptions {
  /**
   * Wait for the lead-in clips too (bounded by `deadlineMs`). Only the
   * OPENING does: its welcome is the turn's content, not decoration, and the
   * question text is on screen from the first frame either way.
   */
  readonly awaitLeads: boolean;
  readonly deadlineMs: number;
}

export interface SettledTurn {
  /** Lead-in clips to play before the question, in order. */
  readonly leads: readonly string[];
  readonly question: string;
}

/**
 * The question's clip, and whichever lead-in clips are ready to go with it.
 *
 * A lead-in is a `string` when this session already holds its clip, and a
 * promise when it is still being made. On every turn but the opening, a
 * promise that has not settled by the time the QUESTION clip is ready is
 * dropped — it keeps synthesising into the cache for a later turn, but it
 * does not hold this one. So a lead-in costs the patient the seconds it
 * takes to SAY, and never the seconds it takes to MAKE. A lead-in that fails
 * is skipped; only a failed question clip fails the turn's speech.
 */
export async function settleTurnClips(
  question: Promise<string>,
  leads: readonly (string | Promise<string>)[],
  options: SettleOptions,
): Promise<SettledTurn> {
  if (options.awaitLeads) {
    const bounded = Promise.all(
      leads.map((lead) =>
        typeof lead === "string"
          ? Promise.resolve<string | null>(lead)
          : withDeadline(lead, options.deadlineMs).catch(() => null),
      ),
    );
    const uri = await question;
    const ready = await bounded;
    return { leads: ready.filter((lead): lead is string => lead !== null), question: uri };
  }
  const settled: (string | null)[] = leads.map((lead) => (typeof lead === "string" ? lead : null));
  leads.forEach((lead, index) => {
    if (typeof lead !== "string") {
      lead.then(
        (uri) => {
          settled[index] = uri;
        },
        () => undefined, // a lead-in that failed is simply not said
      );
    }
  });
  const uri = await question;
  return { leads: settled.filter((lead): lead is string => lead !== null), question: uri };
}
