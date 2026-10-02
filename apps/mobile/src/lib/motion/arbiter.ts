/**
 * The arbiter and the commit window (INT-334, MOTION-5;
 * docs/design/motion/motion-verification.md §4 MOTION-5, §2.1 #5–#7 and #20;
 * intake-voice-motion-spec.md §3.3 ARB-1…ARB-5; files/02 §5.2a rules 1 and 8;
 * ADR-033 §2, Proposed).
 *
 * Pure — no React Native, Reanimated or clock — so every rule is a reducer
 * the node suite can drive through thousands of sequences. A consumer
 * (INT-337's dialogue wiring) asks it what to do with each commit and applies
 * the answer; nothing here animates.
 *
 * The rules:
 * - **One app-authored animation at any instant** (02 §5.2a rule 8). The order
 *   is a named tuple with no priority numbers.
 * - **Snap, never queue.** An arrival of strictly higher priority snaps the
 *   running element to its end state, then animates. An equal or lower one
 *   renders instantly. Nothing waits behind an animation, so motion never
 *   delays content.
 * - **Hold, never rest.** Every class except RED only holds the ambient loop,
 *   frozen at its current value, and it resumes from there when the transient
 *   ends. Snapping a loop back to rest is a visible jump. Only RED stops it,
 *   and a stopped loop stays stopped.
 * - **The commit window.** YELLOW, work chips and rail commits wait while the
 *   patient is listening or the composer has focus (not "while a draft
 *   exists", which would hold YELLOW back behind an abandoned draft). They are
 *   applied at the next window in priority order — one animates, the rest
 *   render instantly — and never dropped. A slot invalidated meanwhile is
 *   never rendered, so nothing appears and then vanishes. RED and content
 *   never wait.
 * - **RED** has no motion of its own (lib/motion/red.ts). It renders at once,
 *   snaps whatever is running, stops the ambient loop and ignores the window.
 *   "Preempt" belongs to RED alone (invariant 9). A DEFERRED_CLINICIAN finding
 *   is never sent here: its caller keys the RED commit on the presentation
 *   mode, never on the arrival of a RED event (S-6).
 *
 * `release` is the end of an animation, reported by its consumer. A late
 * report for an element that was already snapped is ignored.
 */
import type { StreamTurn } from "../dialogue/stream";

/** The arbiter's order, highest first. Extends 02 §5.2a rule 8. */
export const ARBITER_ORDER = [
  "red",
  "yellowPill",
  "workChip",
  "railCommit",
  "content",
  "ambient",
] as const;

export type ArbiterClass = (typeof ARBITER_ORDER)[number];

/** Every class that arrives as a commit. `ambient` is the loop, never a commit. */
export type CommitClass = Exclude<ArbiterClass, "ambient">;

/** One state change a consumer wants to show. */
export interface Commit {
  readonly cls: CommitClass;
  /** The element's identity: a later commit with the same id replaces it. */
  readonly id: string;
  /** The slot it fills, for invalidation (a transcript line, a chip). */
  readonly slot?: string;
}

/** The ambient loop: free, frozen at its current value, or gone for good. */
export type AmbientLoop = "running" | "held" | "stopped";

export interface ArbiterState {
  /** The one element animating now, or none. Never RED. */
  readonly running: { readonly cls: CommitClass; readonly id: string } | null;
  readonly ambient: AmbientLoop;
  /** Commit-window commits waiting for the next window, in arrival order. */
  readonly deferred: readonly Commit[];
}

export const EMPTY_ARBITER: ArbiterState = { running: null, ambient: "running", deferred: [] };

/** What happens to one commit: it fades in, it simply appears, or it waits. */
export type Render = "animate" | "instant" | "deferred";

export interface Decision {
  readonly state: ArbiterState;
  readonly render: Render;
  /** The id of the running element snapped to its end state, if one was. */
  readonly snapped: string | null;
}

export interface Window {
  readonly open: boolean;
}

const WINDOW_CLASSES: ReadonlySet<CommitClass> = new Set(["yellowPill", "workChip", "railCommit"]);

/** Whether a class waits for the commit window. RED and content never do. */
export function waitsForWindow(cls: CommitClass): boolean {
  return WINDOW_CLASSES.has(cls);
}

export interface WindowInputs {
  readonly turnPhase: StreamTurn["phase"];
  /** The typed composer has focus: the patient is mid-sentence. */
  readonly composerFocused: boolean;
}

/** The commit window: closed while the patient is listening or composing. */
export function windowOpen({ turnPhase, composerFocused }: WindowInputs): boolean {
  return turnPhase !== "listening" && !composerFocused;
}

function rank(cls: ArbiterClass): number {
  return ARBITER_ORDER.indexOf(cls);
}

function withoutId(deferred: readonly Commit[], id: string): readonly Commit[] {
  return deferred.filter((c) => c.id !== id);
}

/** Decide one commit, now. */
export function arbitrate(state: ArbiterState, commit: Commit, window: Window): Decision {
  if (commit.cls === "red") {
    return {
      state: { running: null, ambient: "stopped", deferred: state.deferred },
      render: "instant",
      snapped: state.running?.id ?? null,
    };
  }
  if (waitsForWindow(commit.cls) && !window.open) {
    const index = state.deferred.findIndex((c) => c.id === commit.id);
    const deferred =
      index < 0
        ? [...state.deferred, commit]
        : state.deferred.map((c, i) => (i === index ? commit : c));
    return { state: { ...state, deferred }, render: "deferred", snapped: null };
  }
  // A commit that is applied now supersedes any deferred copy of itself.
  const deferred = withoutId(state.deferred, commit.id);
  const current = state.running;
  if (current !== null && rank(commit.cls) >= rank(current.cls)) {
    return { state: { ...state, deferred }, render: "instant", snapped: null };
  }
  return {
    state: {
      running: { cls: commit.cls, id: commit.id },
      ambient: state.ambient === "stopped" ? "stopped" : "held",
      deferred,
    },
    render: "animate",
    snapped: current?.id ?? null,
  };
}

/** The animation of `id` ended. The ambient loop resumes if it was only held. */
export function release(state: ArbiterState, id: string): ArbiterState {
  if (state.running === null || state.running.id !== id) {
    return state;
  }
  return {
    ...state,
    running: null,
    ambient: state.ambient === "held" ? "running" : state.ambient,
  };
}

/** Drop every deferred commit that fills `slot`: it will never be rendered. */
export function invalidate(state: ArbiterState, slot: string): ArbiterState {
  if (!state.deferred.some((c) => c.slot === slot)) {
    return state;
  }
  return { ...state, deferred: state.deferred.filter((c) => c.slot !== slot) };
}

export interface Applied {
  readonly commit: Commit;
  readonly render: Exclude<Render, "deferred">;
  readonly snapped: string | null;
}

export interface Flush {
  readonly state: ArbiterState;
  readonly applied: readonly Applied[];
}

/**
 * At a window, apply every deferred commit in priority order (arrival order
 * within a class). The first may animate under the usual rules; each one
 * after it is equal or lower, so it renders instantly. A shut window applies
 * nothing.
 */
export function flush(state: ArbiterState, window: Window): Flush {
  if (!window.open || state.deferred.length === 0) {
    return { state, applied: [] };
  }
  const ordered = state.deferred
    .map((commit, arrival) => ({ commit, arrival }))
    .sort((a, b) => rank(a.commit.cls) - rank(b.commit.cls) || a.arrival - b.arrival)
    .map((entry) => entry.commit);
  let next: ArbiterState = { ...state, deferred: [] };
  const applied: Applied[] = [];
  for (const commit of ordered) {
    const decision = arbitrate(next, commit, window);
    next = decision.state;
    applied.push({
      commit,
      render: decision.render === "animate" ? "animate" : "instant",
      snapped: decision.snapped,
    });
  }
  return { state: next, applied };
}
