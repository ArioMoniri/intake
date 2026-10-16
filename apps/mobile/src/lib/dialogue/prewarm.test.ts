/**
 * INT-440 — the session pre-warm, ordered and bounded.
 *
 * The pre-warm used to fire every question's clip at once. With George in
 * front, that is N simultaneous vendor syntheses against a per-patient budget
 * (dev_voice_guard: 30 tokens, 0.5 per second) and the vendor's own concurrency
 * limit: the overflow came back 429/502 and dropped, silently, to the
 * self-hosted lane — so one visit was asked in two different voices. Clips now
 * warm in question order (the next question is always the next one asked for)
 * with at most PREWARM_CONCURRENCY in flight.
 */
import { describe, expect, it } from "vitest";

import { nextQuestionAfter, PREWARM_CONCURRENCY, warmInOrder } from "./prewarm";

describe("nextQuestionAfter — the clip worth preloading while this one plays", () => {
  const qs = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];

  it("is the next question in pack order", () => {
    expect(nextQuestionAfter(qs, 0, [])).toEqual({ id: "b" });
  });

  it("skips questions already asked", () => {
    expect(nextQuestionAfter(qs, 0, ["b", "c"])).toEqual({ id: "d" });
  });

  it("is null at the end of the pack", () => {
    expect(nextQuestionAfter(qs, 3, [])).toBeNull();
    expect(nextQuestionAfter(qs, 1, ["c", "d"])).toBeNull();
  });
});

function deferred() {
  let resolve: () => void = () => undefined;
  let reject: (error: Error) => void = () => undefined;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function flush(): Promise<void> {
  for (let i = 0; i < 5; i += 1) {
    await Promise.resolve();
  }
}

describe("warmInOrder", () => {
  it("starts work in item order and never exceeds the limit", async () => {
    const started: number[] = [];
    const gates = new Map<number, ReturnType<typeof deferred>>();
    let inFlight = 0;
    let peak = 0;
    const done = warmInOrder([1, 2, 3, 4, 5], 2, async (n) => {
      started.push(n);
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      const gate = deferred();
      gates.set(n, gate);
      await gate.promise;
      inFlight -= 1;
    });
    await flush();
    expect(started).toEqual([1, 2]);
    gates.get(1)?.resolve();
    await flush();
    expect(started).toEqual([1, 2, 3]);
    for (const n of [2, 3, 4, 5]) {
      gates.get(n)?.resolve();
      await flush();
    }
    await done;
    expect(started).toEqual([1, 2, 3, 4, 5]);
    expect(peak).toBe(2);
  });

  it("a failed item never stops the rest, and the whole never rejects", async () => {
    const seen: number[] = [];
    await expect(
      warmInOrder([1, 2, 3], 1, async (n) => {
        seen.push(n);
        if (n === 1) {
          throw new Error("tts_unreachable");
        }
      }),
    ).resolves.toBeUndefined();
    expect(seen).toEqual([1, 2, 3]);
  });

  it("starts nothing new once the session is stale", async () => {
    const seen: number[] = [];
    let stale = false;
    await warmInOrder(
      [1, 2, 3, 4],
      1,
      async (n) => {
        seen.push(n);
        if (n === 2) {
          stale = true;
        }
      },
      () => stale,
    );
    expect(seen).toEqual([1, 2]);
  });

  it("treats a limit below one as one", async () => {
    const seen: number[] = [];
    await warmInOrder([1, 2], 0, async (n) => {
      seen.push(n);
    });
    expect(seen).toEqual([1, 2]);
  });

  it("bounds the session at the smallest vendor concurrency", () => {
    expect(PREWARM_CONCURRENCY).toBe(2);
  });
});
