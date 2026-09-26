/**
 * The reduce-motion store (INT-331, MOTION-2;
 * docs/design/motion/motion-verification.md §3 S-2, §4 MOTION-2).
 *
 * Pure and dependency-injected: the OS arrives as a `ReduceMotionSource`, so
 * the whole policy is node-testable and no react-native import reaches it.
 * The device half is native/reduceMotionSource.ts, reached only through a
 * lazy import (see `deferredReduceMotionSource`).
 *
 * It replaces a hook that failed OPEN. Each of its call sites started at
 * `false` and animated until its own OS read came back, and each one asked
 * the OS and listened for itself. This store fails CLOSED:
 *
 * - one OS read and one OS listener, started by the first subscriber and
 *   shared by every later one;
 * - the snapshot is `null` until the OS has answered, and stays `null` when a
 *   read is refused, throws or answers something that is not a boolean.
 *   `reducedMotion` in lib/prefs/appearance reads `null` as reduced, so
 *   nothing animates until the OS says it may;
 * - a failed re-read keeps the last known answer: it neither reverts to
 *   unknown nor guesses;
 * - a change event reaches every subscriber, and a read that settles after a
 *   newer event or read cannot undo it;
 * - the app re-reads on return to the foreground, where a change made in
 *   Settings meanwhile may not have produced an event;
 * - the last unsubscribe releases the OS listeners. With nothing listening a
 *   change could be missed, so the answer is forgotten as well: the next
 *   subscriber starts from reduced, with a fresh read.
 */

/** The OS setting, as the store needs it. */
export interface ReduceMotionSource {
  /** Whether the OS asks for reduced motion. */
  read(): Promise<boolean>;
  /** The OS setting changed while the app is running. */
  onChange(cb: (reduced: boolean) => void): () => void;
  /** The app returned to the foreground; the store re-reads. */
  onForeground(cb: () => void): () => void;
}

export interface ReduceMotionStore {
  /** The first subscriber starts ONE read and ONE listener. */
  subscribe(listener: () => void): () => void;
  /** `null`: the OS has not answered, and that means reduced. */
  getSnapshot(): boolean | null;
}

/** Call an OS registration; a source that throws registers nothing. */
function attach(register: () => () => void): () => void {
  try {
    return register();
  } catch {
    return () => undefined;
  }
}

export function createReduceMotionStore(source: ReduceMotionSource): ReduceMotionStore {
  let answer: boolean | null = null;
  /** One entry per subscription, so the same callback twice counts twice. */
  const subscriptions = new Set<{ readonly listener: () => void }>();
  let release: (() => void) | null = null;
  /** Orders reads and events: an answer older than the one applied is dropped. */
  let issued = 0;
  let applied = 0;

  function nextTicket(): number {
    issued += 1;
    return issued;
  }

  function publish(next: boolean): void {
    if (next === answer) {
      return;
    }
    answer = next;
    for (const { listener } of [...subscriptions]) {
      listener();
    }
  }

  function read(): void {
    const ticket = nextTicket();
    const accept = (value: unknown): void => {
      if (ticket > applied && typeof value === "boolean") {
        applied = ticket;
        publish(value);
      }
    };
    let pending: Promise<boolean>;
    try {
      pending = source.read();
    } catch {
      return;
    }
    // A refused read changes nothing: `null` stays reduced, and a known
    // answer stays known.
    void Promise.resolve(pending).then(accept, () => undefined);
  }

  function start(): void {
    const offChange = attach(() =>
      source.onChange((reduced) => {
        if (release === null || typeof reduced !== "boolean") {
          return;
        }
        applied = nextTicket();
        publish(reduced);
      }),
    );
    const offForeground = attach(() => source.onForeground(read));
    release = () => {
      offChange();
      offForeground();
    };
    read();
  }

  function stop(): void {
    const releasing = release;
    release = null;
    // Drop every read still in flight: it belongs to a subscription that
    // has ended, and nothing now hears a change that could supersede it.
    applied = nextTicket();
    answer = null;
    releasing?.();
  }

  return {
    subscribe(listener) {
      const subscription = { listener };
      subscriptions.add(subscription);
      if (release === null) {
        start();
      }
      return () => {
        if (!subscriptions.delete(subscription)) {
          return;
        }
        if (subscriptions.size === 0) {
          stop();
        }
      };
    },
    getSnapshot() {
      return answer;
    },
  };
}

/**
 * A source whose device adapter is loaded on first use.
 *
 * This is how lib/a11y/prefs.ts reaches native/reduceMotionSource.ts: through
 * a lazy `import()`, so the adapter, and react-native with it, never sits on
 * a static import path that a node test could follow. The adapter is loaded
 * once. If it fails to load, every read is refused and the answer stays
 * reduced. A listener released before the adapter arrives is never attached.
 */
export function deferredReduceMotionSource(
  load: () => Promise<ReduceMotionSource>,
): ReduceMotionSource {
  let loading: Promise<ReduceMotionSource> | null = null;
  const loaded = (): Promise<ReduceMotionSource> => {
    if (loading === null) {
      try {
        loading = load();
      } catch (error) {
        loading = Promise.reject(error);
      }
    }
    return loading;
  };

  function later(register: (source: ReduceMotionSource) => () => void): () => void {
    let released = false;
    let off: (() => void) | null = null;
    void loaded().then(
      (source) => {
        if (!released) {
          off = attach(() => register(source));
        }
      },
      () => undefined,
    );
    return () => {
      released = true;
      off?.();
      off = null;
    };
  }

  return {
    read: () => loaded().then((source) => source.read()),
    onChange: (cb) => later((source) => source.onChange(cb)),
    onForeground: (cb) => later((source) => source.onForeground(cb)),
  };
}
