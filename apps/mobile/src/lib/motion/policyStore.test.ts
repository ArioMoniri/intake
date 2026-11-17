/**
 * The reduce-motion store (INT-331, MOTION-2;
 * docs/design/motion/motion-verification.md §3 S-2, §4 MOTION-2).
 *
 * The defect this replaces failed OPEN: every consumer of the old hook
 * started at `useState(false)` and animated until its own OS read came back,
 * one read and one listener per call site. The store fails CLOSED: until the
 * OS has answered, and whenever a read is refused, the answer is `null`, and
 * `reducedMotion` reads `null` as reduced.
 *
 * London school: the OS is a fake source handed in, so every property here
 * is proved in node without a device. The native adapter
 * (native/reduceMotionSource.ts) is a thin, untested shim over
 * AccessibilityInfo and AppState.
 */
import { describe, expect, it, vi } from "vitest";

import { reducedMotion } from "../prefs/appearance";
import {
  createReduceMotionStore,
  deferredReduceMotionSource,
  type ReduceMotionSource,
} from "./policyStore";

interface FakeOs extends ReduceMotionSource {
  /** How many times the OS was asked. */
  readonly reads: () => number;
  /** Live listeners on the OS change event and on the foreground event. */
  readonly changeListeners: () => number;
  readonly foregroundListeners: () => number;
  /** Settle the oldest outstanding read. */
  answer(value: unknown): void;
  refuse(): void;
  change(value: boolean): void;
  foreground(): void;
}

function fakeOs(): FakeOs {
  const pending: { resolve: (value: boolean) => void; reject: (error: Error) => void }[] = [];
  const change = new Set<(reduced: boolean) => void>();
  const foreground = new Set<() => void>();
  let reads = 0;
  return {
    reads: () => reads,
    changeListeners: () => change.size,
    foregroundListeners: () => foreground.size,
    read() {
      reads += 1;
      return new Promise<boolean>((resolve, reject) => pending.push({ resolve, reject }));
    },
    onChange(cb) {
      const own = (reduced: boolean) => cb(reduced);
      change.add(own);
      return () => {
        change.delete(own);
      };
    },
    onForeground(cb) {
      const own = () => cb();
      foreground.add(own);
      return () => {
        foreground.delete(own);
      };
    },
    answer(value) {
      pending.shift()?.resolve(value as boolean);
    },
    refuse() {
      pending.shift()?.reject(new Error("isReduceMotionEnabled rejected"));
    },
    change(value) {
      for (const cb of [...change]) {
        cb(value);
      }
    },
    foreground() {
      for (const cb of [...foreground]) {
        cb();
      }
    },
  };
}

/** Let every settled promise deliver. */
const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe("the reduce-motion store (MOTION-2 · S-2: fail closed)", () => {
  it("reads the OS once however many consumers subscribe", async () => {
    const os = fakeOs();
    const store = createReduceMotionStore(os);
    const consumers = Array.from({ length: 7 }, () => store.subscribe(() => undefined));
    os.answer(false);
    await settle();

    expect(os.reads()).toBe(1);
    expect(os.changeListeners()).toBe(1);
    expect(os.foregroundListeners()).toBe(1);
    expect(store.getSnapshot()).toBe(false);

    // Consumers arriving after the answer share it; they never ask again.
    const late = store.subscribe(() => undefined);
    expect(os.reads()).toBe(1);
    expect(store.getSnapshot()).toBe(false);
    [...consumers, late].forEach((unsubscribe) => unsubscribe());
  });

  it("an unanswered OS read resolves to reduced", async () => {
    const os = fakeOs();
    const store = createReduceMotionStore(os);
    // Before anyone subscribes, and while the only read is still in flight.
    expect(store.getSnapshot()).toBeNull();
    expect(reducedMotion(false, store.getSnapshot())).toBe(true);
    const unsubscribe = store.subscribe(() => undefined);
    await settle();
    expect(os.reads()).toBe(1);
    expect(store.getSnapshot()).toBeNull();
    expect(reducedMotion(false, store.getSnapshot())).toBe(true);
    unsubscribe();
  });

  it("a rejected OS read resolves to reduced, never to motion", async () => {
    const os = fakeOs();
    const store = createReduceMotionStore(os);
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    os.refuse();
    await settle();
    expect(store.getSnapshot()).toBeNull();
    expect(reducedMotion(false, store.getSnapshot())).toBe(true);
    expect(listener).not.toHaveBeenCalled();

    // An answer that is not a boolean is not an answer either.
    os.foreground();
    os.answer(undefined);
    await settle();
    expect(store.getSnapshot()).toBeNull();
    unsubscribe();

    // A source that throws instead of rejecting takes nothing down.
    const throwing = createReduceMotionStore({
      read: () => {
        throw new Error("native module missing");
      },
      onChange: () => {
        throw new Error("native module missing");
      },
      onForeground: () => {
        throw new Error("native module missing");
      },
    });
    const release = throwing.subscribe(() => undefined);
    await settle();
    expect(throwing.getSnapshot()).toBeNull();
    expect(reducedMotion(false, throwing.getSnapshot())).toBe(true);
    release();
  });

  it("a failed re-read keeps the last known answer", async () => {
    for (const known of [false, true]) {
      const os = fakeOs();
      const store = createReduceMotionStore(os);
      const unsubscribe = store.subscribe(() => undefined);
      os.answer(known);
      await settle();
      expect(store.getSnapshot()).toBe(known);

      os.foreground();
      expect(os.reads()).toBe(2);
      os.refuse();
      await settle();
      // It does not revert to unknown, and it does not guess.
      expect(store.getSnapshot()).toBe(known);
      unsubscribe();
    }
  });

  it("a change event updates every snapshot", async () => {
    const os = fakeOs();
    const store = createReduceMotionStore(os);
    const seen: (boolean | null)[][] = [[], [], []];
    const unsubscribes = seen.map((log) => store.subscribe(() => log.push(store.getSnapshot())));
    os.answer(false);
    await settle();

    os.change(true);
    expect(store.getSnapshot()).toBe(true);
    os.change(false);
    expect(store.getSnapshot()).toBe(false);
    for (const log of seen) {
      expect(log).toEqual([false, true, false]);
    }

    // The same answer twice is not a change, so no consumer re-renders.
    os.change(false);
    for (const log of seen) {
      expect(log).toHaveLength(3);
    }
    unsubscribes.forEach((unsubscribe) => unsubscribe());
  });

  it("a read that settles after a newer change event does not undo it", async () => {
    const os = fakeOs();
    const store = createReduceMotionStore(os);
    const unsubscribe = store.subscribe(() => undefined);
    // The first read is still in flight when the patient turns the setting on.
    os.change(true);
    os.answer(false);
    await settle();
    expect(store.getSnapshot()).toBe(true);
    unsubscribe();
  });

  it("re-reads on return to foreground", async () => {
    const os = fakeOs();
    const store = createReduceMotionStore(os);
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    os.answer(false);
    await settle();
    expect(listener).toHaveBeenCalledTimes(1);

    // Changed in Settings while the app was in the background.
    os.foreground();
    expect(os.reads()).toBe(2);
    os.answer(true);
    await settle();
    expect(store.getSnapshot()).toBe(true);
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it("the last unsubscribe releases the OS listener", async () => {
    const os = fakeOs();
    const store = createReduceMotionStore(os);
    const first = vi.fn();
    const second = vi.fn();
    const releaseFirst = store.subscribe(first);
    const releaseSecond = store.subscribe(second);
    os.answer(false);
    await settle();

    releaseFirst();
    releaseFirst(); // a repeated release must not take another consumer's place
    expect(os.changeListeners()).toBe(1);
    expect(os.foregroundListeners()).toBe(1);

    releaseSecond();
    expect(os.changeListeners()).toBe(0);
    expect(os.foregroundListeners()).toBe(0);

    // Nothing is listening any more, so the answer is no longer known: the
    // store falls back to reduced rather than trusting a stale "motion".
    expect(store.getSnapshot()).toBeNull();
    first.mockClear();
    second.mockClear();
    os.change(true);
    expect(first).not.toHaveBeenCalled();
    expect(second).not.toHaveBeenCalled();

    // A new consumer starts one fresh read and one fresh listener.
    const again = store.subscribe(() => undefined);
    expect(os.reads()).toBe(2);
    expect(os.changeListeners()).toBe(1);
    os.answer(true);
    await settle();
    expect(store.getSnapshot()).toBe(true);
    again();
  });
});

describe("the lazily loaded native source", () => {
  it("a native source that fails to load resolves to reduced", async () => {
    const store = createReduceMotionStore(
      deferredReduceMotionSource(() => Promise.reject(new Error("chunk failed to load"))),
    );
    const unsubscribe = store.subscribe(() => undefined);
    await settle();
    expect(store.getSnapshot()).toBeNull();
    expect(reducedMotion(false, store.getSnapshot())).toBe(true);
    unsubscribe();
  });

  it("loads the adapter once, and forwards the OS through it", async () => {
    const os = fakeOs();
    const load = vi.fn(() => Promise.resolve<ReduceMotionSource>(os));
    const store = createReduceMotionStore(deferredReduceMotionSource(load));
    const unsubscribes = [store.subscribe(() => undefined), store.subscribe(() => undefined)];
    await settle();
    expect(load).toHaveBeenCalledTimes(1);
    expect(os.reads()).toBe(1);
    expect(os.changeListeners()).toBe(1);
    expect(os.foregroundListeners()).toBe(1);

    os.answer(false);
    await settle();
    expect(store.getSnapshot()).toBe(false);
    os.change(true);
    expect(store.getSnapshot()).toBe(true);

    unsubscribes.forEach((unsubscribe) => unsubscribe());
    expect(os.changeListeners()).toBe(0);
    expect(os.foregroundListeners()).toBe(0);
  });

  it("an unsubscribe before the adapter loads attaches nothing", async () => {
    const os = fakeOs();
    let deliver: (source: ReduceMotionSource) => void = () => undefined;
    const store = createReduceMotionStore(
      deferredReduceMotionSource(
        () =>
          new Promise<ReduceMotionSource>((resolve) => {
            deliver = resolve;
          }),
      ),
    );
    const unsubscribe = store.subscribe(() => undefined);
    unsubscribe();
    deliver(os);
    await settle();
    expect(os.changeListeners()).toBe(0);
    expect(os.foregroundListeners()).toBe(0);
  });
});
