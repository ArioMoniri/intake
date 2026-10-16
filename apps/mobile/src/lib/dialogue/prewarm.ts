/**
 * The session pre-warm, ordered and bounded (INT-440). Pure and node-testable.
 *
 * The pre-warm used to fire every question's clip at once. With George in
 * front, that was N simultaneous vendor syntheses against a per-patient budget
 * (services/api dev_voice_guard: 30 tokens, refilled at 0.5 a second) and the
 * vendor's own concurrency limit; the overflow came back 429/502 and fell,
 * silently, to the self-hosted lane — one visit, two voices. Clips now warm in
 * question order, so the next question asked is always the next one warmed,
 * with at most PREWARM_CONCURRENCY in flight.
 */

/**
 * The question most likely asked after `step` — the next one in pack order not
 * yet asked — so its clip can be loaded into a player while this one plays
 * (INT-440: no load on the turn). A guess, never a decision: gates may skip
 * it, and a missed guess only costs the load it would have saved.
 */
export function nextQuestionAfter<Q extends { readonly id: string }>(
  questions: readonly Q[],
  step: number,
  asked: readonly string[],
): Q | null {
  for (let index = step + 1; index < questions.length; index += 1) {
    if (!asked.includes(questions[index].id)) {
      return questions[index];
    }
  }
  return null;
}

/** In-flight clip syntheses during the pre-warm: the smallest concurrency a
 * vendor plan grants, so the warm-up never queues behind its own requests. */
export const PREWARM_CONCURRENCY = 2;

/**
 * Run `work` over `items` in order with at most `limit` in flight. A failed
 * item never stops the rest and the whole never rejects — the speaking driver
 * re-ensures each clip on its own turn and surfaces a real failure there. Once
 * `isStale()` is true no new item starts.
 */
export async function warmInOrder<T>(
  items: readonly T[],
  limit: number,
  work: (item: T) => Promise<unknown>,
  isStale: () => boolean = () => false,
): Promise<void> {
  let next = 0;
  const runner = async (): Promise<void> => {
    while (next < items.length && !isStale()) {
      const item = items[next];
      next += 1;
      try {
        await work(item);
      } catch {
        // surfaced by the speaking driver on its own ensure
      }
    }
  };
  const runners = Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, runner);
  await Promise.all(runners);
}
