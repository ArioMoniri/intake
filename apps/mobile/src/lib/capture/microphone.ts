/**
 * The one microphone a screen holds (INT-559): at most one capture turn, one
 * open in flight that every driver shares, and a discard that reaches the
 * open wherever it is suspended.
 *
 * The dialogue (useDialogueSession.ts) and the voice-note pill
 * (VoiceNote.tsx) prepare the platform's audio session before a capture turn
 * exists, so a discard that lands during that prepare — the app leaving the
 * foreground, a typed answer, an unmount — has no turn to reach, and the
 * review of #964 found the open going on to start a microphone no one owned.
 * So every discard advances a generation, and an open reads it after every
 * await (INT-551's pattern, one level above the turn): a moved generation
 * ends the open where it stands, and the turn it made reads the same check
 * as its `closed`, so the session stops at its next await or chunk. The
 * prepare step and the turn factory are ports, so every interleaving runs in
 * node (microphone.test.ts).
 *
 * Invariant 3: whatever is held or opening when `discard` runs ends without
 * capturing, without a listener, with its stream stopped and released, and
 * with nothing sent.
 */
import type { CaptureTurn } from "./turn";

export interface MicrophoneDeps {
  /** Bring the platform's audio session up for capture. */
  prepare: () => Promise<void>;
  /**
   * A capture turn for one open. `closed` turns true when that open is
   * abandoned or the owner closes; the turn reads it after every await.
   */
  createTurn: (closed: () => boolean) => CaptureTurn;
  /** The owner has closed for good: a RED, a leave, a terminal turn, an unmount. */
  closed: () => boolean;
}

export interface Microphone {
  /**
   * Open the microphone unless the owner has closed or one is capturing; a
   * caller arriving while an open is in flight shares it. Resolves to whether
   * it is capturing; rejects when the platform fails an open nobody abandoned.
   */
  open(): Promise<boolean>;
  readonly capturing: boolean;
  /** The turn held right now, opening or capturing; null when none. */
  current(): CaptureTurn | null;
  /**
   * Hand the held turn over to be finished, which the caller does next; an
   * open still in flight is abandoned, so nothing opens behind the hand-over.
   */
  take(): CaptureTurn | null;
  /** Close whatever is open or opening and zero it; nothing is sent. */
  discard(): void;
}

export function createMicrophone(deps: MicrophoneDeps): Microphone {
  let held: CaptureTurn | null = null;
  let opening: Promise<boolean> | null = null;
  /** Advances on every discard, and on a hand-over mid-open: an open begun before it is abandoned. */
  let generation = 0;

  const abandonOpening = () => {
    generation += 1;
    // The next open starts fresh rather than joining the abandoned one.
    opening = null;
  };

  const open = (): Promise<boolean> => {
    if (opening !== null) {
      return opening;
    }
    if (held?.capturing === true) {
      return Promise.resolve(true);
    }
    if (deps.closed()) {
      return Promise.resolve(false);
    }
    const mine = generation;
    const abandoned = () => deps.closed() || generation !== mine;
    const run = (async () => {
      try {
        await deps.prepare();
        if (abandoned()) {
          return false;
        }
        const turn = deps.createTurn(abandoned);
        held = turn;
        let opened = false;
        try {
          opened = await turn.open();
        } finally {
          if (!opened && held === turn) {
            held = null;
          }
        }
        return opened && held === turn;
      } catch (error) {
        if (abandoned()) {
          // Whoever abandoned this open has moved on; nothing of it is left open.
          return false;
        }
        throw error;
      }
    })();
    opening = run;
    const settle = () => {
      if (opening === run) {
        opening = null;
      }
    };
    run.then(settle, settle);
    return run;
  };

  return {
    open,
    get capturing() {
      return held?.capturing === true;
    },
    current: () => held,
    take() {
      if (opening !== null) {
        abandonOpening();
      }
      const turn = held;
      held = null;
      return turn;
    },
    discard() {
      abandonOpening();
      const turn = held;
      held = null;
      turn?.discard();
    },
  };
}
